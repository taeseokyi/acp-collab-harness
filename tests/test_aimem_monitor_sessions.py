# -*- coding: utf-8 -*-
"""웹 모니터 reader 가 세션 폴더(`.aimem/sessions/<id>/`)를 옛 실행(`.aimem/runs/`)과 같은 꼴로 보이는지.

임시 루트만 쓴다 - 진짜 `.aimem/` 는 건드리지 않고 읽지도 않는다. 진짜 하네스는 뜨지 않는다.
"""
import _fleet_env  # noqa: F401  (맨 위: 어댑터 선택을 fake 로)

import datetime
import json
import os
import pathlib
import tempfile
import unittest

from aimem_monitor import reader
from fleet_rt import sessions

NOW = datetime.datetime(2026, 11, 12, 12, 0, 0)
LEGACY_KEYS = {"id", "slot", "harness", "model", "label", "rev", "write", "started", "state", "rc",
               "elapsed_sec", "report_head", "task", "project", "round"}
NEW_KEYS = {"session_state", "fail_kind", "last_event_at", "last_event", "provider", "role"}

RUN_ID = "T-263-S2-a1-193012"


_STARTED = []


def tearDownModule():
    for p in _STARTED:
        p.kill()
        p.wait()


def mk_session(root, sid, *, end=None, running=False, report=None, events=(), stderr=None, brief="지시문",
               started="2026-11-12T11:00:00", harness="fake", extra=None):
    d = root / ".aimem" / "sessions" / sid
    d.mkdir(parents=True)
    meta = {"id": sid, "role": "worker", "harness": harness, "model": "m1", "provider": "kisti", "slot": "S2",
            "task_id": "T-263", "round": 21, "label": "라벨", "started": started, "write_paths": ["a.py"],
            "extra": extra or {"rev": "163", "project": "proj"}}
    if running:
        # 살아 있는 감독은 세션 표식(환경변수)을 가진 프로세스여야 한다 - pid 만으로는 인정하지 않는다
        import subprocess
        p = subprocess.Popen(["sleep", "60"], env={**os.environ, "AIFLEET_SESSION": sid,
                                                   "AIFLEET_SESSIONS_ROOT": os.path.abspath(root / ".aimem" / "sessions")})
        _STARTED.append(p)
        meta["supervisor_pid"] = p.pid
        meta["proc_start"] = sessions.proc_start(p.pid)
    else:
        meta["supervisor_pid"] = 2 ** 22 + 12345    # 없는 pid
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "brief.md").write_text(brief, encoding="utf-8")
    if events:
        (d / "events.jsonl").write_text("\n".join(f"{at}\t{raw}" for at, raw in events) + "\n", encoding="utf-8")
    if stderr is not None:
        (d / "stderr.log").write_text(stderr, encoding="utf-8")
    if report is not None:
        (d / "report.md").write_text(report, encoding="utf-8")
    if end is not None:
        (d / "end.json").write_text(json.dumps(end), encoding="utf-8")
    return d


def mk_legacy(root, rid, rc=0):
    r = root / ".aimem" / "runs"
    r.mkdir(parents=True, exist_ok=True)
    (r / f"{rid}.json").write_text(json.dumps({"id": rid, "slot": "S1", "harness": "codex", "model": "x",
                                               "started": "2026-11-12T10:00:00"}), encoding="utf-8")
    (r / f"{rid}.out").write_text("옛 보고", encoding="utf-8")
    (r / f"{rid}.rc").write_text(str(rc), encoding="utf-8")


def ev(**kw):
    return json.dumps(kw, ensure_ascii=False)


class SessionRows(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = pathlib.Path(self._t.name)
        mk_legacy(self.root, "20261109-172618-S3")
        mk_session(self.root, "T-1-S2-a1-100000", running=True, started="2026-11-12T11:50:00", events=[
            ("2026-11-12T11:50:05", ev(type="text", text="시작")),
            ("2026-11-12T11:55:09", ev(type="tool", name="Bash", summary="ls")),
            ("2026-11-12T11:55:10", ev(type="usage", tokens_in=1, tokens_out=2))])
        mk_session(self.root, "T-2-S2-a1-100000", report="DONE\n" + "가" * 300,
                   end={"state": "done", "rc": 0, "ended": "2026-11-12T11:10:00", "fail_kind": None, "why": None})
        mk_session(self.root, "T-3-S2-a1-100000", report="BLOCKED x",
                   end={"state": "failed", "rc": 3, "ended": "2026-11-12T11:05:00", "fail_kind": "work", "why": "w"})
        mk_session(self.root, "T-4-S2-a1-100000", events=[("2026-11-12T11:20:00", ev(type="text", text="말"))],
                   end={"state": "stalled", "rc": None, "ended": "2026-11-12T11:30:00", "fail_kind": "timeout", "why": "침묵"})
        mk_session(self.root, "T-5-S2-a1-100000",
                   end={"state": "killed", "rc": None, "ended": "2026-11-12T11:40:00", "fail_kind": None, "why": "cancel"})
        mk_session(self.root, "T-6-S2-a1-100000", end={"state": "timeout", "rc": None,
                   "ended": "2026-11-12T11:45:00", "fail_kind": "timeout", "why": "t"})
        mk_session(self.root, "T-7-S2-a1-100000")   # end.json 없고 감독 사라짐 -> lost
        errors = []
        self.rows = {r["id"]: r for r in reader._collect_runs(self.root, NOW, errors)}
        self.errors = errors

    def test_all_listed_with_keys(self):
        self.assertEqual(len(self.rows), 8)
        self.assertEqual(self.errors, [])
        for r in self.rows.values():
            self.assertTrue((LEGACY_KEYS | NEW_KEYS) <= set(r), r["id"])

    def test_legacy_row_has_none_new_keys(self):
        r = self.rows["20261109-172618-S3"]
        self.assertEqual((r["state"], r["rc"]), ("done", 0))
        for k in NEW_KEYS:
            self.assertIsNone(r[k], k)

    def test_running(self):
        r = self.rows["T-1-S2-a1-100000"]
        self.assertEqual((r["state"], r["rc"], r["session_state"]), ("running", None, "running"))
        self.assertEqual(r["elapsed_sec"], 600)
        self.assertEqual(r["last_event_at"], "2026-11-12T11:55:10")
        self.assertEqual(r["last_event"], "[tool] Bash: ls")   # usage 줄은 건너뛴다
        self.assertEqual((r["provider"], r["role"]), ("kisti", "worker"))
        self.assertEqual((r["rev"], r["project"], r["task"], r["round"]), ("163", "proj", "T-263", 21))
        self.assertEqual(r["write"], ["a.py"])

    def test_done_with_report(self):
        r = self.rows["T-2-S2-a1-100000"]
        self.assertEqual((r["state"], r["rc"], r["session_state"]), ("done", 0, "done"))
        self.assertEqual(r["elapsed_sec"], 600)
        self.assertEqual(len(r["report_head"]), reader.REPORT_HEAD)
        self.assertTrue(r["report_head"].startswith("DONE"))

    def test_failed_keeps_rc_and_kind(self):
        r = self.rows["T-3-S2-a1-100000"]
        self.assertEqual((r["state"], r["rc"], r["session_state"], r["fail_kind"]), ("done", 3, "failed", "work"))

    def test_stalled_and_timeout(self):
        a, b = self.rows["T-4-S2-a1-100000"], self.rows["T-6-S2-a1-100000"]
        self.assertEqual((a["state"], a["rc"], a["session_state"], a["fail_kind"]), ("done", 125, "stalled", "timeout"))
        self.assertEqual((b["state"], b["rc"], b["session_state"]), ("done", 124, "timeout"))
        self.assertEqual(a["last_event"], "[text] 말")

    def test_killed_and_lost(self):
        k, l = self.rows["T-5-S2-a1-100000"], self.rows["T-7-S2-a1-100000"]
        self.assertEqual((k["state"], k["rc"], k["session_state"]), ("lost", None, "killed"))
        self.assertEqual(k["elapsed_sec"], 2400)   # end.json.ended 에서 멈춘다
        self.assertEqual((l["state"], l["session_state"]), ("lost", "lost"))
        self.assertIsNotNone(l["elapsed_sec"])      # 마지막 흔적(파일 mtime)에서 멈춘다

    def test_last_event_capped(self):
        d = mk_session(self.root, "T-8-S2-a1-100000", running=True,
                       events=[("2026-11-12T11:59:00", ev(type="text", text="길" * 400))])
        r = {x["id"]: x for x in reader._collect_runs(self.root, NOW, [])}["T-8-S2-a1-100000"]
        self.assertLessEqual(len(r["last_event"]), 120)
        self.assertTrue(d.is_dir())

    def test_last_activity_uses_given_root_not_repo(self):
        """lost 의 끝 시각은 임시 루트의 세션에서 구한다 (진짜 저장소의 `.aimem/sessions` 가 아니라)."""
        got = reader._last_activity(self.root, "T-5-S2-a1-100000")
        self.assertEqual(got, datetime.datetime(2026, 11, 12, 11, 40, 0))
        self.assertIsNone(reader._last_activity(self.root, "nope-1"))

    def test_temp_root_never_reads_real_repo(self):
        empty = pathlib.Path(tempfile.mkdtemp(dir=self._t.name))
        self.assertEqual(reader._collect_runs(empty, NOW, []), [])
        real = pathlib.Path(reader.__file__).resolve().parents[2] / ".aimem" / "sessions"
        ids = {r["id"] for r in reader._collect_runs(self.root, NOW, [])}
        if real.is_dir():
            self.assertFalse({p.name for p in real.iterdir()} & ids)


class SessionDetail(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = pathlib.Path(self._t.name)
        mk_session(self.root, RUN_ID, brief="지시 본문\n확인토큰: abcdef", stderr="\x1b[31m경고\x1b[0m\n",
                   report="DONE\n끝", events=[
                       ("2026-11-12T11:00:01", ev(type="text", text="안녕")),
                       ("2026-11-12T11:00:02", ev(type="tool", name="Bash", summary="ls")),
                       ("2026-11-12T11:00:03", "쓰레기 줄"),
                       ("2026-11-12T11:00:04", ev(type="usage", tokens_in=1, tokens_out=1)),
                       ("2026-11-12T11:00:05", ev(type="error", text="재접속", retry=True))],
                   end={"state": "failed", "rc": 2, "ended": "2026-11-12T11:30:00", "fail_kind": "infra", "why": "x"})
        mk_legacy(self.root, "20261109-172618-S3")

    def test_detail(self):
        d = reader.run_detail(RUN_ID, self.root)
        self.assertEqual(set(d), set(reader.DETAIL_KEYS))
        self.assertTrue(d["found"])
        self.assertEqual((d["status"], d["rc"], d["slot"], d["harness"], d["model"]), ("done", 2, "S2", "fake", "m1"))
        self.assertEqual(d["ended"], "2026-11-12T11:30:00")
        self.assertEqual(d["elapsed_s"], 1800)
        self.assertIn("지시 본문", d["brief"])
        self.assertNotIn("abcdef", d["brief"])        # 확인토큰 가림
        self.assertEqual(d["stderr_tail"], "경고")
        self.assertEqual(d["report"], "DONE\n끝")
        for k in ("out", "err", "rc", "brief"):
            self.assertTrue(d["paths"][k], k)
        self.assertEqual(d["errors"], [])

    def test_events_rendering(self):
        out = reader.run_events(RUN_ID, self.root)
        self.assertEqual(out.splitlines(), [
            "11:00:01  [text] 안녕", "11:00:02  [tool] Bash: ls", "11:00:05  [error] 재접속"])

    def test_legacy_detail_unchanged(self):
        d = reader.run_detail("20261109-172618-S3", self.root)
        self.assertTrue(d["found"])
        self.assertEqual((d["status"], d["rc"], d["report"]), ("done", 0, "옛 보고"))
        self.assertEqual(reader.run_events("20261109-172618-S3", self.root), "")

    def test_missing_in_temp_root(self):
        d = reader.run_detail("T-999-S2-a1-123456", self.root)
        self.assertFalse(d["found"])

    def test_symlinked_session_not_followed(self):
        real = self.root / ".aimem" / "sessions" / RUN_ID
        link = self.root / ".aimem" / "sessions" / "T-9-S2-a1-111111"
        link.symlink_to(real, target_is_directory=True)
        self.assertFalse(reader.run_detail("T-9-S2-a1-111111", self.root)["found"])


if __name__ == "__main__":
    unittest.main()
