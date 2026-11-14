"""프로젝트 (2026-11-10 태석님 지시) - 여러 라운드를 묶는 단위. 요청마다 프로젝트를 고르고,
결과물은 `projects/<이름>/` 한 곳에 쌓인다. 여기서는 요청의 `project` 필드와 목록을 지킨다."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

from aimem_monitor import REQUEST_ROW_KEYS, SERVER_KEYS, server  # noqa: E402


class ProjectTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)

    def create(self, **kw):
        payload = {"title": "제목", "detail": "본문", "requester": "태석"}
        payload.update(kw)
        return server.create_request(payload, self.root)

    def record(self, res):
        return json.loads((self.root / res["path"]).read_text(encoding="utf-8"))

    def test_project_is_stored_and_blank_means_fleet_itself(self):
        ok, res = self.create(project="  reefwiz-앱 ")
        self.assertTrue(ok, res)
        self.assertEqual(self.record(res)["project"], "reefwiz-앱")
        for blank in ({}, {"project": ""}, {"project": None}, {"project": "   "}):
            ok, res = self.create(**blank)
            self.assertTrue(ok, res)
            self.assertEqual(self.record(res)["project"], "")

    def test_project_name_must_be_a_single_safe_folder_name(self):
        for bad in ("../etc", "a/b", "a\\b", ".hidden", "a.b", "두 낱말", "-앞대시", "x" * 41, ["a"], 7, "a\x00b", "줄\n바꿈"):
            with self.subTest(bad=repr(bad)):
                ok, res = self.create(project=bad)
                self.assertFalse(ok)
                self.assertIn("프로젝트", res["error"])
        self.assertFalse((self.root / ".aimem" / "requests").exists() and any((self.root / ".aimem" / "requests").iterdir()))

    def test_list_projects_merges_folders_and_requested_names(self):
        (self.root / "projects" / "있는것").mkdir(parents=True)
        (self.root / "projects" / "bad name").mkdir()
        (self.root / "projects" / "file.txt").write_text("x", encoding="utf-8")
        (self.root / "outside").mkdir()
        (self.root / "projects" / "link").symlink_to(self.root / "outside")
        self.create(project="새것")
        self.create()
        got = server.list_projects(self.root)
        self.assertEqual([(p["name"], p["path"], p["exists"]) for p in got],
                         [("새것", "projects/새것/", False), ("있는것", "projects/있는것/", True)])
        self.assertEqual(got[0]["requests"], {"total": 1, "done": 0, "new": 1, "active": 0})
        self.assertEqual((got[0]["percent"], got[1]["percent"], got[1]["rounds"]), (0.0, None, []))

    def test_progress_counts_requests_rounds_and_latest_note(self):
        d = self.root / "projects" / "알파"
        d.mkdir(parents=True)
        (d / "PROGRESS.md").write_text(
            "# 알파\n\n## R8 (2026-11-11)\n- 한 일: 화면\n- 남은 일: 배포\n\n## R7 (2026-11-10)\n- 한 일: 골격\n", encoding="utf-8")
        for n, projs in ((7, ["알파"]), (8, ["알파", "베타"]), (9, ["알파"])):
            r = self.root / "rounds" / f"R{n}"
            r.mkdir(parents=True)
            (r / "round.json").write_text(json.dumps({"round": n, "at": f"2026-11-1{n - 7}T09:00:00", "projects": projs}),
                                          encoding="utf-8")
        (self.root / "rounds" / "R9" / "round.json").write_text("{깨진", encoding="utf-8")     # 깨진 기록은 건너뛴다
        arch = self.root / ".aimem" / "archive" / "requests-2026-11"
        arch.mkdir(parents=True)
        (arch / "old.json").write_text(json.dumps({"id": "Q-1", "project": "알파", "status": "DONE"}), encoding="utf-8")
        reqs = [{"id": "a", "project": "알파", "status": "DONE"},
                {"id": "b", "project": "알파", "status": "IN-PROGRESS", "progress_pct": 50},
                {"id": "c", "project": "알파", "status": "NEW"},
                {"id": "d", "project": "알파", "status": "REJECTED"},
                {"id": "e", "project": "", "status": "NEW"},
                {"id": "f", "project": "../x", "status": "NEW"}]
        got = {p["name"]: p for p in server.list_projects(self.root, reqs)}
        self.assertEqual(sorted(got), ["알파"])       # 베타는 폴더도 열린 요청도 없이 라운드 기록에만 있다 - 싣지 않는다
        a = got["알파"]
        self.assertEqual(a["requests"], {"total": 4, "done": 2, "new": 1, "active": 1})   # 거절은 빼고, 아카이브된 완료는 센다
        self.assertEqual(a["percent"], 62.5)                                              # (100+100+50+0)/4
        self.assertEqual((a["rounds"], a["round_count"], a["last_round"]), ([7, 8], 2, 8))
        self.assertEqual(a["last_round_at"], "2026-11-11T09:00:00")
        self.assertTrue(a["summary"].startswith("## R8"))
        self.assertIn("남은 일: 배포", a["summary"])
        self.assertNotIn("R7", a["summary"])

    def test_a_project_whose_folder_was_removed_leaves_the_list(self):
        """폴더를 지우는 것이 프로젝트를 치우는 것 - 끝난 요청·라운드 기록이 남아 있어도 목록에 없다."""
        (self.root / "projects" / "산것").mkdir(parents=True)
        for where, n in (("rounds", 4), (".aimem/archive/rounds-2026-10", 3)):
            r = self.root / where / f"R{n}"
            r.mkdir(parents=True)
            (r / "round.json").write_text(json.dumps({"round": n, "at": "2026-10-01T09:00:00", "projects": ["산것", "치운것"]}),
                                          encoding="utf-8")
        arch = self.root / ".aimem" / "archive" / "requests-2026-10"
        arch.mkdir(parents=True)
        (arch / "old.json").write_text(json.dumps({"id": "Q-1", "project": "치운것", "status": "DONE"}), encoding="utf-8")
        reqs = [{"id": "a", "project": "치운것", "status": "DONE"}, {"id": "b", "project": "치운것", "status": "REJECTED"}]
        got = {p["name"]: p for p in server.list_projects(self.root, reqs)}
        self.assertEqual(sorted(got), ["산것"])
        self.assertEqual(got["산것"]["rounds"], [3, 4])            # 정리로 내려간 라운드 기록도 센다
        # 폴더가 아직 없는 새 프로젝트는 열린 요청이 있어 보인다
        got = server.list_projects(self.root, reqs + [{"id": "c", "project": "치운것", "status": "NEW"}])
        self.assertEqual([(p["name"], p["exists"], p["requests"]["total"]) for p in got], [("산것", True, 0), ("치운것", False, 3)])

    def test_progress_is_against_goals_when_the_manager_wrote_them(self):
        """REV 148: 요청을 다 끝내도 프로젝트가 덜 됐으면 100% 가 아니어야 한다 - `## 목표` 체크리스트 기준."""
        d = self.root / "projects" / "알파"
        d.mkdir(parents=True)
        reqs = [{"id": "a", "project": "알파", "status": "DONE"}]
        a = server.list_projects(self.root, reqs)[0]
        self.assertEqual((a["percent"], a["basis"], a["goals"], a["request_percent"]), (100.0, "requests", None, 100.0))
        (d / "PROGRESS.md").write_text(
            "# 알파\n\n## 목표\n- [x] 골격\n- [X] 로그인 화면\n  - [ ] 하위 항목도 센다\n* [ ] 배포\n- 체크 없는 줄\n-[ ] 띄어쓰기 없음\n- [ ]\n"
            "\n## R8 (2026-11-11)\n- 한 일: 화면\n- [x] 여기 체크는 목표가 아니다\n- 남은 일: 배포\n", encoding="utf-8")
        a = server.list_projects(self.root, reqs)[0]
        self.assertEqual((a["goals"], a["percent"], a["basis"], a["request_percent"]),
                         ({"total": 4, "done": 2}, 50.0, "goals", 100.0))
        self.assertEqual(a["rounds"], [8])
        self.assertTrue(a["summary"].startswith("## R8"))                 # 최근 기록은 여전히 라운드 항목
        (d / "PROGRESS.md").write_text("# 알파\n\n## Goals (예측)\n- [x] a\n- [x] b\n", encoding="utf-8")
        self.assertEqual(server.list_projects(self.root, [])[0]["percent"], 100.0)
        for empty in ("# 알파\n\n## 목표\n아직 못 정함\n\n## R8\n- [x] x\n", "# 알파\n\n## 목표치 아님\n- [x] x\n"):
            (d / "PROGRESS.md").write_text(empty, encoding="utf-8")       # 항목이 없으면 요청 기준으로 돌아간다
            a = server.list_projects(self.root, reqs)[0]
            self.assertEqual((a["goals"], a["basis"], a["percent"]), (None, "requests", 100.0), empty)

    def test_edit_keeps_project_unless_given(self):
        ok, res = self.create(project="알파")
        rid = res["id"]
        code, _ = server.update_request(rid, {"title": "새 제목", "detail": "d"}, self.root)
        self.assertEqual(code, 200)
        self.assertEqual(self.record(res)["project"], "알파")              # 옛 화면은 project 를 안 보낸다 - 그대로
        code, _ = server.update_request(rid, {"title": "새 제목", "detail": "d", "project": "베타"}, self.root)
        self.assertEqual((code, self.record(res)["project"]), (200, "베타"))
        code, out = server.update_request(rid, {"title": "새 제목", "detail": "d", "project": "../x"}, self.root)
        self.assertEqual(code, 400)
        self.assertEqual(self.record(res)["project"], "베타")
        self.assertEqual(server.request_detail(rid, self.root)[1]["project"], "베타")

    def _project(self):
        d = self.root / "projects" / "알파"
        (d / "src").mkdir(parents=True)
        (d / "README.md").write_text("# 알파\n", encoding="utf-8")
        (d / "PROGRESS.md").write_text("## R7\n- 남은 일\n", encoding="utf-8")
        (d / "src" / "main.py").write_text(f"ROOT = '{self.root}'\n", encoding="utf-8")
        (d / "src" / "logo.bin").write_bytes(b"\x00\x01\x02")
        (d / ".env").write_text("SECRET=1", encoding="utf-8")
        (d / "node_modules").mkdir()
        (d / "node_modules" / "x.js").write_text("x", encoding="utf-8")
        (self.root / "outside.txt").write_text("밖", encoding="utf-8")
        (d / "link.txt").symlink_to(self.root / "outside.txt")
        return d

    def test_project_files_lists_deliverables_only(self):
        self._project()
        code, out = server.project_files("알파", self.root)
        self.assertEqual(code, 200)
        self.assertEqual([f["path"] for f in out["files"]], ["README.md", "PROGRESS.md", "src/logo.bin", "src/main.py"])
        self.assertEqual(server.project_files("없음", self.root)[0], 404)
        self.assertEqual(server.project_files("../x", self.root)[0], 400)

    def test_project_file_reads_text_inside_the_folder_only(self):
        self._project()
        code, out = server.project_file("알파", "src/main.py", self.root)
        self.assertEqual((code, out["binary"], out["truncated"]), (200, False, False))
        self.assertNotIn(str(self.root), out["text"])                    # 저장소 절대 경로는 가려서 나간다
        code, out = server.project_file("알파", "src/logo.bin", self.root)
        self.assertEqual((code, out["binary"], out["text"]), (200, True, ""))
        for bad, want in (("../outside.txt", 400), ("/etc/passwd", 400), ("src/../../outside.txt", 400), (".env", 400),
                          ("link.txt", 404), ("src", 404), ("없는.md", 404), ("", 400), ("src\\main.py", 400)):
            self.assertEqual(server.project_file("알파", bad, self.root)[0], want, bad)

    def test_project_file_is_capped(self):
        d = self._project()
        (d / "big.txt").write_text("가" * 100_000, encoding="utf-8")       # 300KB
        code, out = server.project_file("알파", "big.txt", self.root)
        self.assertEqual((code, out["truncated"]), (200, True))
        self.assertLessEqual(len(out["text"].encode("utf-8")), server.PROJECT_FILE_MAX_BYTES + 3)

    def test_contract_carries_project(self):
        self.assertIn("project", REQUEST_ROW_KEYS)
        self.assertIn("projects", SERVER_KEYS)


class ProjectRemoveApiTest(unittest.TestCase):
    """`POST /api/projects/<이름>/remove` (REV 180) - 미리보기는 쓰기 없음, 실행은 `confirm` 이 이름과 같아야."""

    def setUp(self):
        import contextlib, io
        from unittest import mock
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
        import aimem_db, fleet, fleet_ctl, fleet_graph
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve()
        (self.root / ".aimem" / "requests").mkdir(parents=True)
        (self.root / "projects" / "알파").mkdir(parents=True)
        (self.root / "projects" / "알파" / "a.txt").write_text("x", encoding="utf-8")
        for module, attr, value in ((server, "ROOT", self.root), (fleet, "ROOT", self.root),
                                    (fleet, "RUNS", self.root / ".aimem" / "runs"),
                                    (fleet_graph, "GRAPHS", self.root / ".aimem" / "graph"),
                                    (fleet_ctl, "_aimem_dir", lambda: self.root / ".aimem"),
                                    (aimem_db, "ROOT", self.root), (aimem_db, "DB", self.root / ".aimem" / "aimem.db"),
                                    (aimem_db, "AIMEM", self.root / "AIMEM.md"),
                                    (aimem_db, "HANDOFF", self.root / ".aimem" / "handoff.md")):
            p = mock.patch.object(module, attr, value)
            p.start()
            self.addCleanup(p.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.cmd_init()

    def call(self, name, payload, root=None):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            return server.project_remove_action(name, payload, "웹(t)", root or self.root)

    def test_preview_writes_nothing_and_remove_needs_the_name(self):
        code, res = self.call("알파", {"dry_run": True})
        self.assertEqual((code, res["ok"], res["dry_run"], res["files"]), (200, True, True, 1))
        for payload in ({}, {"confirm": "알파 "}, {"confirm": "베타"}, {"dry_run": False, "confirm": ["알파"]}):
            code, res = self.call("알파", payload)
            self.assertEqual(code, 400, payload)
        code, res = self.call("알파", {"dry_run": "false", "confirm": "알파"})      # 거짓이 아닌 값은 미리보기로 본다
        self.assertEqual((code, res["dry_run"]), (200, True))
        self.assertTrue((self.root / "projects" / "알파" / "a.txt").is_file())
        code, res = self.call("알파", {"dry_run": False, "confirm": "알파"})
        self.assertEqual((code, res["ok"], res["dry_run"]), (200, True, False))
        self.assertFalse((self.root / "projects" / "알파").exists())
        self.assertEqual([p["name"] for p in server.list_projects(self.root)], [])

    def test_refusals(self):
        for bad in ("../알파", "알파/..", "", "a b", None):
            self.assertEqual(self.call(bad, {"dry_run": True})[0], 400, bad)
        self.assertEqual(self.call("없는것", {"dry_run": True})[0], 404)
        self.assertEqual(self.call("없는것", {"confirm": "없는것"})[0], 409)
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        self.assertEqual(self.call("알파", {"confirm": "알파"}, root=other.name)[0], 403)
        self.assertEqual(self.call("알파", ["알파"])[0], 400)
        self.assertTrue((self.root / "projects" / "알파" / "a.txt").is_file())


if __name__ == "__main__":
    unittest.main()
