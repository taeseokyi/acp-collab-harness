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


class MigrateEnglishHandoffTest(AimemDbCliTest):
    """REV 128: `migrate` 가 영어 제목 `## 4. Handoff Log` 아래의 항목도 events(kind=handoff) 로 적재한다."""

    def test_english_section_4_is_imported(self):
        (self.root / "AIMEM.md").write_text(
            "# AIMEM.md\n\n- **REV: 5** (x)\n\n## 4. Handoff Log\n\n"
            "- `2026-11-10 19:00` Claude Code: **REV 5. English entry.** body\n\n## 4.5 Waiting Queue\n", encoding="utf-8")
        aimem_db.migrate(verbose=False)
        row = self.row("SELECT at, rev FROM events WHERE kind='handoff'")
        self.assertEqual((row["at"], row["rev"]), ("2026-11-10 19:00", 5))


class HandoffLogTest(AimemDbCliTest):
    """REV 132: 핸드오프의 정본은 DB events 하나. .aimem/handoff.md 는 최신 12건 생성물, 밀려난 항목은 아카이브로 내보낸다."""

    def handoff_count(self):
        with aimem_db.connect() as con:
            return con.execute("SELECT count(*) FROM events WHERE kind='handoff'").fetchone()[0]

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


class HandoffConcurrencyTest(HandoffLogTest):
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
