"""NEW 요청 웹 수정과 요청 전문 조회 (요청 Q-261110-549a, 2026-11-10 클로드 코드).

- NEW·미분담 요청만 제목·본문을 고칠 수 있다. 요청자·상태·분담은 그대로
- 분담이 시작됐거나 NEW 가 아니면 409, 없으면 404, 형식 오류는 400
- 파일은 이름이 아니라 **내용의 id** 로 찾는다 (접두가 같은 다른 파일, 심볼릭 링크 무시)
- 전문 조회는 600자 절단 없이 돌려주고 editable 을 알려 준다
- 라우트 정규식이 경로 탈출 꼴을 받지 않는다
"""
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import server  # noqa: E402


class RequestEditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.reqs = self.root / ".aimem" / "requests"
        self.reqs.mkdir(parents=True)

    def put(self, rid, status="NEW", subtasks=None, name=None, detail="본문"):
        rec = {"id": rid, "created": "2026-11-10T10:00:00", "requester": "태석", "title": "원래 제목",
               "detail": detail, "status": status, "subtasks": subtasks or []}
        f = self.reqs / (name or f"{rid}-x.json")
        f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return f

    def test_edit_new_request_updates_title_and_detail_only(self):
        f = self.put("Q-261110-aaaa")
        code, body = server.update_request("Q-261110-aaaa", {"title": "새 제목", "detail": "줄1\n줄2",
                                                             "requester": "공격자", "status": "DONE"}, self.root)
        self.assertEqual(code, 200, body)
        rec = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual((rec["title"], rec["detail"]), ("새 제목", "줄1\n줄2"))
        self.assertEqual((rec["requester"], rec["status"]), ("태석", "NEW"))
        self.assertIn("edited", rec)

    def test_edit_refused_after_assignment(self):
        self.put("Q-261110-bbbb", subtasks=[{"id": "T-1"}])
        self.put("Q-261110-cccc", status="IN-PROGRESS")
        for rid in ("Q-261110-bbbb", "Q-261110-cccc"):
            code, _ = server.update_request(rid, {"title": "x"}, self.root)
            self.assertEqual(code, 409, rid)

    def test_edit_validation_and_missing(self):
        self.put("Q-261110-dddd")
        self.assertEqual(server.update_request("Q-261110-dddd", {"title": "  "}, self.root)[0], 400)
        self.assertEqual(server.update_request("Q-261110-dddd", {"title": "t", "detail": ["x"]}, self.root)[0], 400)
        self.assertEqual(server.update_request("Q-261110-dddd", ["x"], self.root)[0], 400)
        self.assertEqual(server.update_request("Q-261110-eeee", {"title": "t"}, self.root)[0], 404)

    def test_matches_content_id_not_filename_prefix(self):
        other = self.put("Q-261110-ffff", name="Q-261110-ffff-copy.json")
        rec = json.loads(other.read_text(encoding="utf-8")); rec["id"] = "Q-999999-zzzz"
        other.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(server.update_request("Q-261110-ffff", {"title": "t"}, self.root)[0], 404)

    @unittest.skipIf(os.name != "posix", "symlink")
    def test_symlink_request_file_ignored(self):
        real = self.root / "outside.json"
        real.write_text(json.dumps({"id": "Q-261110-1111", "status": "NEW", "subtasks": []}), encoding="utf-8")
        (self.reqs / "Q-261110-1111-link.json").symlink_to(real)
        self.assertEqual(server.update_request("Q-261110-1111", {"title": "t"}, self.root)[0], 404)
        self.assertNotIn("t", json.loads(real.read_text(encoding="utf-8")).get("title", ""))

    def test_detail_returns_full_text_and_editable(self):
        long = "가" * 2000
        self.put("Q-261110-2222", detail=long)
        code, body = server.request_detail("Q-261110-2222", self.root)
        self.assertEqual(code, 200)
        self.assertEqual(len(body["detail"]), 2000)
        self.assertTrue(body["editable"])
        self.put("Q-261110-3333", status="DONE")
        self.assertFalse(server.request_detail("Q-261110-3333", self.root)[1]["editable"])
        self.assertEqual(server.request_detail("Q-261110-4444", self.root)[0], 404)

    def test_route_regexes_reject_traversal(self):
        good = ["/api/requests/Q-261110-abcd", "/api/requests/20261109-170155-582a"]
        bad = ["/api/requests/../etc", "/api/requests/Q-261110-abcd/../x", "/api/requests/Q-261110-ABCD",
               "/api/requests/Q-261110-abcd*", "/api/requests/"]
        for p in good:
            self.assertTrue(server._REQ_GET_RE.match(p), p)
            self.assertTrue(server._REQ_EDIT_RE.match(p + "/edit"), p)
        for p in bad:
            self.assertIsNone(server._REQ_GET_RE.match(p), p)
            self.assertIsNone(server._REQ_EDIT_RE.match(p + "/edit"), p)


class ManagerStatusCacheTest(unittest.TestCase):
    def test_cleared_timestamp_with_value_does_not_crash(self):
        """함대 제어가 `_mgr_cache['at']` 만 비운 상태에서 /api/state 가 TypeError 로 죽던 것 (2026-11-10)."""
        with server._mgr_lock:
            saved = dict(server._mgr_cache)
            server._mgr_cache.update({"at": None, "value": {"ok": True, "sessions": [], "error": None},
                                      "refreshing": True})
        try:
            out = server.manager_status(server.ROOT)
            self.assertTrue(out["pending"])
            self.assertIsNone(out["age_sec"])
        finally:
            with server._mgr_lock:
                server._mgr_cache.clear()
                server._mgr_cache.update(saved)


if __name__ == "__main__":
    unittest.main()
