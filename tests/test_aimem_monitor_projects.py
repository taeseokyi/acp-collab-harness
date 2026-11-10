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
        self.assertEqual(sorted(got), ["베타", "알파"])
        a = got["알파"]
        self.assertEqual(a["requests"], {"total": 4, "done": 2, "new": 1, "active": 1})   # 거절은 빼고, 아카이브된 완료는 센다
        self.assertEqual(a["percent"], 62.5)                                              # (100+100+50+0)/4
        self.assertEqual((a["rounds"], a["round_count"], a["first_round"], a["last_round"]), ([7, 8], 2, 7, 8))
        self.assertEqual(a["last_round_at"], "2026-11-11T09:00:00")
        self.assertTrue(a["summary"].startswith("## R8"))
        self.assertIn("남은 일: 배포", a["summary"])
        self.assertNotIn("R7", a["summary"])
        b = got["베타"]
        self.assertEqual((b["exists"], b["rounds"], b["percent"], b["summary"]), (False, [8], None, ""))

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


if __name__ == "__main__":
    unittest.main()
