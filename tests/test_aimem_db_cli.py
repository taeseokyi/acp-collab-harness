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
import os
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
            "artifacts": None, "detail": None, "requester": None, "days": 14, "dry_run": False, "project": None}
    base.update(kw)
    return argparse.Namespace(**base)

# `python3 -m unittest … 2>&1 | tail -3` 의 마지막 줄이 `OK` 이게 합니다 (2026-11-11 R11 T-139).
# 이 파일의 시험이 부르는 명령들이 표준출력에 찍는 줄(`ok: …aimem.db`, 린터 결과)은 파이프에서 버퍼에 있다가
# unittest 요약 **뒤에** 나와, `tail -3 | grep '^OK'` 로 건 검증이 멀쩡한 작업을 실패로 판정했습니다.
_QUIET = []


def setUpModule():
    import contextlib
    import io
    cm = contextlib.redirect_stdout(io.StringIO())
    cm.__enter__()
    _QUIET.append(cm)


def tearDownModule():
    while _QUIET:
        _QUIET.pop().__exit__(None, None, None)


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
        """REV 148: `round.json` 은 띄울 때의 열린 요청만 담았다 - 도중에 들어온 요청의 프로젝트가 라운드에서 빠졌다."""
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
        """2026-11-11 태석님: '지금 끝난 것 전부' 미리보기가 안 됨. 노드의 `task` 가 지시 본문 전체일 때 그것을
        입력 파일 이름으로 써서 `File name too long` 으로 죽었다(14일 기준에서는 최근 그래프가 걸러져 안 보였다)."""
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


    # 결함 10: 본문에 `**REV N` 이 없는 항목도 rev 가 비지 않고, 파일 차례(최신 먼저)가 유지된다.
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


class ArchiveAttachedRecordsTest(AimemDbCliTest):
    """REV 157: 끝난 작업을 정리할 때 그 작업에 딸린 실행·이벤트·핸드오프·전달·로그도 함께 옮긴다."""

    OLD = "2026-01-01T00:00:00"

    def _task(self, tid, status, updated=None):
        updated = updated or self.OLD
        with aimem_db.connect() as con:
            con.execute("INSERT INTO tasks(id,title,slot,status,created,updated) VALUES(?,?,?,?,?,?)",
                        (tid, "제목", "S1", status, updated, updated))
            con.commit()

    def _run(self, rid, task, started=None, rc=True):
        started = started or self.OLD
        d = self.root / ".aimem" / "runs"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{rid}.json").write_text(json.dumps({"id": rid, "task": task, "started": started}), encoding="utf-8")
        (d / f"{rid}.out").write_text("x", encoding="utf-8")
        (d / f"{rid}.brief.md").write_text("x", encoding="utf-8")
        if rc:
            (d / f"{rid}.rc").write_text("0", encoding="utf-8")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO runs(id,task_id,slot,started,rc,state) VALUES(?,?,?,?,?,?)",
                        (rid, task, "S1", started, 0 if rc else None, "done" if rc else "running"))
            con.commit()

    def _event(self, body, at=None, kind="note", rev=None):
        with aimem_db.connect() as con:
            cur = con.execute("INSERT INTO events(at,actor,rev,kind,body) VALUES(?,?,?,?,?)",
                              (at or self.OLD, "t", rev, kind, body))
            con.commit()
            return cur.lastrowid

    def _handoff(self, i, at, rev=None):
        return self._event(f"entry {i:02d}", at=at, kind="handoff", rev=rev)

    def test_finished_task_runs_move_with_it(self):
        self._task("T-900", "DONE")
        self._run("run-900", "T-900")
        plan = aimem_db.archive_plan(0)
        self.assertEqual([r["id"] for r in plan["runs"]], ["run-900"])
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(out["runs"], ["run-900"])
        self.assertFalse((self.root / ".aimem" / "runs" / "run-900.json").exists())
        dest = self.root / ".aimem" / "archive" / "runs-2026-01"
        for ext in ("json", "rc", "out", "brief.md"):
            self.assertTrue((dest / f"run-900.{ext}").exists(), ext)
        self.assertIsNone(self.row("SELECT 1 FROM runs WHERE id=?", "run-900"))

    def test_open_task_runs_stay(self):
        self._task("T-901", "TODO")
        self._run("run-901", "T-901")
        plan = aimem_db.archive_plan(0)
        self.assertEqual(plan["runs"], [])
        aimem_db.archive_apply(plan, actor="t")
        self.assertTrue((self.root / ".aimem" / "runs" / "run-901.json").exists())
        self.assertIsNotNone(self.row("SELECT 1 FROM runs WHERE id=?", "run-901"))

    def test_running_run_stays_even_for_finished_task(self):
        self._task("T-902", "DONE")
        self._run("run-902", "T-902", rc=False)
        plan = aimem_db.archive_plan(0)
        self.assertEqual(plan["runs"], [])
        aimem_db.archive_apply(plan, actor="t")
        self.assertTrue((self.root / ".aimem" / "runs" / "run-902.json").exists())
        self.assertFalse((self.root / ".aimem" / "runs" / "run-902.rc").exists())

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

    def test_rev_unchanged_and_archive_event_written(self):
        self._task("T-900", "DONE")
        self._run("run-900", "T-900")
        self._event("T-900 note")
        with aimem_db.connect() as con:
            con.execute("INSERT INTO meta(key,value) VALUES('rev','42') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            con.commit()
        plan = aimem_db.archive_plan(0)
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(self.row("SELECT value FROM meta WHERE key='rev'")[0], "42")
        rows = [r["body"] for r in self.row_all("SELECT body FROM events WHERE kind='archive'")]
        self.assertEqual(len(rows), 1)
        self.assertIn(f"실행 {len(out['runs'])}건", rows[0])
        self.assertIn(f"이벤트 {len(out['events'])}건", rows[0])

    def row_all(self, sql, *args):
        with aimem_db.connect() as con:
            return con.execute(sql, args).fetchall()

    def test_dry_run_leaves_runs_events_and_logs(self):
        self._task("T-900", "DONE")
        self._run("run-900", "T-900")
        self._event("T-900 note")
        fleet = self.root / ".aimem" / "fleet-mode.log"
        fleet.write_text("2026-01-01T00:00:00 old\n", encoding="utf-8")
        out = self.run_cmd(aimem_db.cmd_archive, days=0, dry_run=True, actor="t")
        self.assertIn("실행 <- 1건", out)
        self.assertIn("이벤트 <- 1건", out)
        self.assertTrue((self.root / ".aimem" / "runs" / "run-900.json").exists())
        self.assertIsNotNone(self.row("SELECT 1 FROM runs WHERE id=?", "run-900"))
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

    def test_running_graph_protects_finished_node_run(self):
        self._task("T-1", "DONE")
        self._run("run-1", "T-1")
        self._graph("G-1", [
            {"id": "T-1", "task": "T-1", "status": "done", "attempts": [{"run_id": "run-1"}]},
            {"id": "T-2", "task": "T-2", "status": "running", "attempts": []},
        ])
        plan = aimem_db.archive_plan(0)
        self.assertEqual([r["id"] for r in plan["runs"]], [])
        aimem_db.archive_apply(plan, actor="t")
        self.assertTrue((self.root / ".aimem" / "runs" / "run-1.json").exists())
        self.assertIsNotNone(self.row("SELECT 1 FROM runs WHERE id=?", "run-1"))

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

    def test_running_graph_protects_off_board_node_run(self):
        self._run("run-3", "T-3")
        self._graph("G-1", [
            {"id": "T-3", "task": "T-3", "status": "done", "attempts": [{"run_id": "run-3"}]},
            {"id": "T-2", "task": "T-2", "status": "running", "attempts": []},
        ])
        plan = aimem_db.archive_plan(0)
        self.assertEqual([r["id"] for r in plan["runs"]], [])
        aimem_db.archive_apply(plan, actor="t")
        self.assertTrue((self.root / ".aimem" / "runs" / "run-3.json").exists())
        self.assertIsNotNone(self.row("SELECT 1 FROM runs WHERE id=?", "run-3"))

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
        """결함 2/X8: 정리 뒤에도 열어 둔 핸들의 새 줄이 파일에 남고 inode 가 같아야 한다."""
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
        """결함 2/X9: 모니터 서버가 monitor.log 를 쥐고 있으면 apply 도 손대지 않는다."""
        aimem = self.root / ".aimem"
        log = aimem / "monitor.log"
        log.write_text("2026-01-01T00:00:00 old\n", encoding="utf-8")
        (aimem / "monitor.pid").write_text(str(os.getpid()), encoding="utf-8")
        plan = aimem_db.archive_plan(0)
        entry = [x for x in plan["logs"] if x["file"] == "monitor.log"][0]
        self.assertEqual(entry["lines"], 0)
        aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(log.read_text(encoding="utf-8"), "2026-01-01T00:00:00 old\n")

    def test_rc_moved_last_so_plan_rediscovers_after_failure(self):
        """결함 4/X1 -> N1: 이동 차례는 `.json` 이 아니라 `.rc` 가 맨 마지막이다. 그래서 어느 replace 가
        죽어도 `.rc` 없는 `.json` 이 남지 않고, 다음 계획이나 고아 줍기가 그 실행을 받아 간다.
        (고치기 전 차례 - brief, out, rc - 로 돌아가면 첫 단언이 빨개진다.)"""
        self._task("T-900", "DONE")
        self._run("run-900", "T-900")
        d = self.root / ".aimem" / "runs"
        real_replace = pathlib.Path.replace
        calls = []

        def spy_replace(self_path, target):
            calls.append(self_path.name)
            return real_replace(self_path, target)

        plan = aimem_db.archive_plan(0)
        self.assertEqual([r["id"] for r in plan["runs"]], ["run-900"])
        with mock.patch("pathlib.Path.replace", spy_replace):
            aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(calls, ["run-900.brief.md", "run-900.json", "run-900.out", "run-900.rc"])
        self.assertEqual(list(d.iterdir()), [])
        dest = self.root / ".aimem" / "archive" / "runs-2026-01"
        for ext in ("json", "rc", "out", "brief.md"):
            self.assertTrue((dest / f"run-900.{ext}").exists(), ext)

        # 셋째 replace(out)에서 죽인다: `.json` 은 이미 옮겨졌고 `.rc` 는 남아 있으므로
        # `.rc` 없는 `.json` 이 남는 일이 없다. 다음 계획이 남은 조각을 줍는다.
        self._task("T-901", "DONE")
        self._run("run-901", "T-901")
        calls.clear()

        def flaky_replace(self_path, target):
            calls.append(self_path.name)
            if len(calls) == 3:
                raise OSError("replace 실패")
            return real_replace(self_path, target)

        with mock.patch("pathlib.Path.replace", flaky_replace):
            with self.assertRaises(OSError):
                aimem_db.archive_apply(aimem_db.archive_plan(0), actor="t")
        self.assertEqual(calls[:3], ["run-901.brief.md", "run-901.json", "run-901.out"])
        self.assertFalse((d / "run-901.json").exists())
        self.assertTrue((d / "run-901.rc").exists())
        self.assertEqual([r["id"] for r in aimem_db.archive_plan(0)["runs"]], ["run-901"])
        aimem_db.archive_apply(aimem_db.archive_plan(0), actor="t")
        self.assertEqual(list(d.iterdir()), [])

    def test_orphan_rc_and_out_are_reclaimed(self):
        """결함 4/X2: `.json` 없는 고아 `.rc/.out` 도 계획이 주워 간다."""
        d = self.root / ".aimem" / "runs"
        d.mkdir(parents=True)
        for name, text in (("run-777.out", "x"), ("run-777.rc", "0")):
            f = d / name
            f.write_text(text, encoding="utf-8")
            os.utime(f, (946684800, 946684800))
        plan = aimem_db.archive_plan(0)
        self.assertEqual([r["id"] for r in plan["runs"]], ["run-777"])
        out = aimem_db.archive_apply(plan, actor="t")
        self.assertEqual(out["runs"], ["run-777"])
        self.assertFalse((d / "run-777.out").exists())
        self.assertFalse((d / "run-777.rc").exists())
        dest = self.root / ".aimem" / "archive" / "runs-2000-01"
        self.assertTrue((dest / "run-777.out").exists())
        self.assertTrue((dest / "run-777.rc").exists())

    def _fail_archiving_run_at(self, k):
        """k 번째 `Path.replace` 에서 죽인 뒤 다시 돌려 `runs/` 가 비는지 본다 (N1)."""
        self._task("T-900", "DONE")
        self._run("run-900", "T-900")
        d = self.root / ".aimem" / "runs"
        real_replace = pathlib.Path.replace
        calls = []

        def flaky_replace(self_path, target):
            calls.append(self_path.name)
            if len(calls) == k:
                raise OSError(f"replace {k} 실패")
            return real_replace(self_path, target)

        with mock.patch("pathlib.Path.replace", flaky_replace):
            with self.assertRaises(OSError):
                aimem_db.archive_apply(aimem_db.archive_plan(0), actor="t")
        expected = ["run-900.brief.md", "run-900.json", "run-900.out", "run-900.rc"]
        self.assertEqual(calls[:k], expected[:k], f"k={k}: 옛 차례(json 마지막)면 여기서 빨개진다")
        # 고친 뒤에는 `.rc` 가 맨 마지막이라 `.rc` 없는 `.json` 이 남지 않는다.
        if (d / "run-900.json").exists():
            self.assertTrue((d / "run-900.rc").exists(), f"k={k}: .rc 없는 .json 이 남았다")
        self.assertEqual([r["id"] for r in aimem_db.archive_plan(0)["runs"]], ["run-900"], f"k={k}")
        aimem_db.archive_apply(aimem_db.archive_plan(0), actor="t")
        self.assertEqual(list(d.iterdir()), [], f"k={k}: 다시 돌린 뒤에도 runs/ 가 비지 않았다")

    def test_failure_at_first_replace_is_recovered_by_next_plan(self):
        """N1 k=1(brief): 아직 아무것도 옮기지 않았고 `.json`+`.rc` 가 남아 다음 계획이 줍는다."""
        self._fail_archiving_run_at(1)

    def test_failure_at_second_replace_is_recovered_by_next_plan(self):
        """N1 k=2(json): brief 만 옮겨졌고 `.json`+`.rc` 가 남아 다음 계획이 줍는다."""
        self._fail_archiving_run_at(2)

    def test_failure_at_third_replace_is_recovered_by_next_plan(self):
        """N1 k=3(out): `.json` 은 옮겨졌고 `.rc` 고아가 남아 다음 계획이 줍는다."""
        self._fail_archiving_run_at(3)

    def test_failure_at_fourth_replace_is_recovered_by_next_plan(self):
        """N1 k=4(rc): `.rc` 고아가 남아 다음 계획이 줍는다."""
        self._fail_archiving_run_at(4)

    def test_log_lines_appended_between_read_and_cut_survive(self):
        """N2: 로그를 읽은 뒤 자르기 전에 다른 프로세스가 `O_APPEND` 로 덧붙인 줄은 원본에 남아야 한다.
        (고치기 전 코드는 `kept` 에 없는 그 줄을 truncate 로 지워 버린다 - 마지막 단언이 빨개진다.)"""
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
        """결함 9/X7: 계획 뒤 다시 열린 태스크 행은 apply 가 내리지 않는다."""
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
        """결함 12/X10·N3: 정리 뒤 AIMEM-state.md 는 다시 쓰이고 AIMEM.md 는 그대로다."""
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
