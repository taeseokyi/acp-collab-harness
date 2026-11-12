"""`aimem_db` 의 `sessions` 색인: init·migrate·state·archive (임시 저장소, 운영 DB 는 건드리지 않는다)."""
import _fleet_env
from fleet_rt import sessions as rt_sessions
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import aimem_db


def dead_pid():
    pid = 4_000_000
    while os.path.exists(f"/proc/{pid}"):
        pid += 1
    return pid


class SessionsDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        (self.root / ".aimem" / "requests").mkdir(parents=True)
        for p in [mock.patch.object(aimem_db, "ROOT", self.root),
                  mock.patch.object(aimem_db, "DB", self.root / ".aimem" / "aimem.db"),
                  mock.patch.object(aimem_db, "AIMEM", self.root / "AIMEM.md"),
                  mock.patch.object(aimem_db, "HANDOFF", self.root / ".aimem" / "handoff.md"),
                  mock.patch.object(aimem_db, "STATE_MD", self.root / "AIMEM-state.md")]:
            p.start()
            self.addCleanup(p.stop)
        self.sdir = self.root / ".aimem" / "sessions"
        self.sdir.mkdir()
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)
        aimem_db.cmd_init()

    def mk(self, sid, pid, end=None, started="2026-01-01T10:00:00", task=None, provider="kisti"):
        d = self.sdir / sid
        d.mkdir()
        if pid == "live":
            pid = _fleet_env.marked_pid(self.sdir, sid)   # 살아 있는 감독 = 그 세션의 표식을 단 프로세스
        (d / "meta.json").write_text(json.dumps({
            "id": sid, "role": "worker", "harness": "opencode", "model": "kisti/kistillm", "provider": provider,
            "slot": "S3", "task_id": task, "attempt": 2, "label": "L", "write_paths": ["a/b"],
            "supervisor_pid": pid, "proc_start": rt_sessions.proc_start(pid), "started": started}), encoding="utf-8")
        (d / "brief.md").write_text("brief", encoding="utf-8")
        if end:
            (d / "end.json").write_text(json.dumps(end), encoding="utf-8")
        return d

    def rows(self):
        with aimem_db.connect() as con:
            return {r["id"]: dict(r) for r in con.execute("SELECT * FROM sessions")}

    def test_init_creates_table(self):
        with aimem_db.connect() as con:
            cols = [r["name"] for r in con.execute("PRAGMA table_info(sessions)")]
        self.assertIn("provider", cols)
        self.assertIn("write_paths", cols)
        aimem_db.cmd_init()   # 멱등

    def test_migrate_indexes_states(self):
        self.mk("run", "live", started="2026-01-01T10:00:03")
        self.mk("fin", dead_pid(), end={"state": "failed", "rc": 2, "ended": "2026-01-01T10:05:00", "fail_kind": "infra"},
                started="2026-01-01T10:00:02")
        self.mk("gone", dead_pid(), started="2026-01-01T10:00:01")
        (self.sdir / "junk").mkdir()
        aimem_db.migrate(verbose=False)
        r = self.rows()
        self.assertEqual(set(r), {"run", "fin", "gone"})
        self.assertEqual(r["run"]["state"], "running")
        self.assertEqual((r["fin"]["state"], r["fin"]["rc"], r["fin"]["fail_kind"], r["fin"]["ended"]),
                         ("failed", 2, "infra", "2026-01-01T10:05:00"))
        self.assertEqual(r["gone"]["state"], "lost")
        self.assertEqual(r["run"]["provider"], "kisti")
        self.assertEqual(json.loads(r["run"]["write_paths"]), ["a/b"])
        self.assertEqual(r["run"]["dir"], str(self.sdir / "run"))

    def test_migrate_idempotent_and_updates_state(self):
        d = self.mk("x", dead_pid())
        aimem_db.migrate(verbose=False)
        self.assertEqual(self.rows()["x"]["state"], "lost")
        with aimem_db.connect() as con:
            con.execute("UPDATE sessions SET tokens_in=7 WHERE id='x'")
            con.commit()
        (d / "end.json").write_text(json.dumps({"state": "done", "rc": 0}), encoding="utf-8")
        aimem_db.migrate(verbose=False)
        aimem_db.migrate(verbose=False)
        r = self.rows()
        self.assertEqual(len(r), 1)
        self.assertEqual((r["x"]["state"], r["x"]["rc"], r["x"]["tokens_in"]), ("done", 0, 7))

    def test_state_dict_merges_runs(self):
        with aimem_db.connect() as con:
            con.execute("INSERT INTO runs(id,task_id,slot,harness,state,started,write_paths) "
                        "VALUES('old','T-1','S1','claude','done','2026-01-01T09:00:00','[]')")
            con.commit()
        self.mk("new", "live", started="2026-01-01T11:00:00")
        aimem_db.migrate(verbose=False)
        st = aimem_db.state_dict()
        self.assertEqual([r["id"] for r in st["runs"]], ["old", "new"])
        new = st["runs"][1]
        for k in ("id", "task_id", "slot", "harness", "model", "attempt", "label", "write_paths", "pid", "started",
                  "ended", "rc", "state", "report_status", "brief_path", "rev"):
            self.assertIn(k, new)
        self.assertEqual(new["write_paths"], ["a/b"])
        self.assertEqual(new["brief_path"], str(self.sdir / "new" / "brief.md"))
        self.assertEqual([s["id"] for s in st["sessions"]], ["new"])
        self.assertEqual(st["sessions"][0]["write_paths"], ["a/b"])
        self.assertIn("new", aimem_db.render_text())   # 렌더가 합친 목록을 그대로 읽는다

    def test_archive_moves_old_finished_only(self):
        end = {"state": "done", "rc": 0, "ended": "2020-01-01T10:05:00"}
        self.mk("old-done", dead_pid(), end=end, started="2020-01-01T10:00:00")
        self.mk("old-run", "live", started="2020-01-01T10:00:00")
        self.mk("old-lost", dead_pid(), started="2020-01-01T10:00:00")
        self.mk("recent", dead_pid(), end=end, started=aimem_db._now())
        aimem_db.migrate(verbose=False)
        plan = aimem_db.archive_plan(14)
        self.assertEqual([s["id"] for s in plan["sessions"]], ["old-done"])
        self.assertGreaterEqual(plan["total_records"], 1)
        out = aimem_db.archive_apply(plan)
        self.assertEqual(out["sessions"], ["old-done"])
        self.assertTrue((self.root / ".aimem" / "archive" / "sessions-2020-01" / "old-done" / "end.json").is_file())
        self.assertFalse((self.sdir / "old-done").exists())
        for keep in ("old-run", "old-lost", "recent"):
            self.assertTrue((self.sdir / keep).is_dir())
        self.assertEqual(set(self.rows()), {"old-run", "old-lost", "recent"})

    def test_archive_skips_open_task(self):
        with aimem_db.connect() as con:
            con.execute("INSERT INTO tasks(id,title,status,updated) VALUES('T-9','t','DOING','2020-01-01T00:00:00')")
            con.commit()
        self.mk("t9", dead_pid(), end={"state": "done", "rc": 0}, started="2020-01-01T10:00:00", task="T-9")
        self.assertEqual(aimem_db.archive_plan(14)["sessions"], [])

    def test_apply_refuses_without_end_json(self):
        d = self.mk("sneaky", dead_pid(), started="2020-01-01T10:00:00")
        out = aimem_db.archive_apply({"cutoff": "2021-01-01T00:00:00", "tasks": [], "requests": [], "graphs": [],
                                      "runs": [], "events": [], "handoff": [], "relay": [], "logs": [],
                                      "sessions": [{"id": "sneaky", "when": "2020-01-01T10:00:00"}]})
        self.assertEqual(out["sessions"], [])
        self.assertTrue(d.is_dir())


if __name__ == "__main__":
    unittest.main()
