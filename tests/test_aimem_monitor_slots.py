"""슬롯 관리 API 계약 (2026-11-10, 태석님 지시 "슬롯 하네스 추가·삭제 + 모델 지정").

`server.slot_action` 은 DB(`aimem_db`)를 고치고, 모델은 openclaw 설정 목록에서만 받는다.
"""
import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import aimem_db  # noqa: E402
from aimem_monitor import server  # noqa: E402

MODELS = {"ok": True, "error": None, "models": [
    {"key": "anthropic/claude-opus-5-5", "name": "opus", "provider": "anthropic", "aliases": ["opus55"], "context": 1000000, "harnesses": ["claude"]},
    {"key": "kisti/kistillm", "name": "KISTI LLM", "provider": "kisti", "aliases": [], "context": 1048576, "harnesses": ["codex", "opencode"]},
]}


class SlotActionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()
        (self.root / ".aimem" / "requests").mkdir(parents=True)
        for target, attr, value in ((aimem_db, "ROOT", self.root), (aimem_db, "DB", self.root / ".aimem" / "aimem.db"),
                                    (server, "ROOT", self.root), (server, "openclaw_models", lambda *a, **k: MODELS),
                                    (server, "_slot_running", lambda slot, root: None)):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.cmd_init()

    def test_add_set_remove_via_api(self):
        code, body = server.slot_action("add", None, {"harness": "claude", "model": "anthropic/claude-opus-5-5", "role": "판단형"}, "웹(test)", self.root)
        self.assertEqual(code, 400)                                       # 역할·비고는 관리자 몫 - 웹은 거절
        self.assertIn("관리자가 정합니다", body["error"])
        code, body = server.slot_action("add", None, {"harness": "claude", "model": "anthropic/claude-opus-5-5"}, "웹(test)", self.root)
        self.assertEqual(code, 201, body)
        self.assertEqual(body["slot"]["slot"], "S1")
        self.assertEqual(body["slot"]["role"], aimem_db.SLOT_ROLE_UNASSIGNED)   # 표식으로 들어간다
        self.assertIn("웹에서 추가", body["slot"]["note"])
        self.assertTrue(body["notice"])                                   # 관리자 통지 요청이 생긴다
        reqs = list((self.root / ".aimem" / "requests").glob("*.json"))
        self.assertEqual(len(reqs), 1)
        import json as _json
        q = _json.loads(reqs[0].read_text(encoding="utf-8"))
        self.assertEqual((q["status"], q["requester"]), ("NEW", server.SLOT_NOTICE_REQUESTER))
        self.assertIn("S1 추가됨", q["title"])
        self.assertNotIn("token", body["slot"])                       # 확인토큰은 공개면에 나가지 않는다
        code, body = server.slot_action("add", None, {"harness": "codex"}, "웹(test)", self.root)
        self.assertEqual((code, body["slot"]["slot"], body["slot"]["model"]), (201, "S2", None))
        code, body = server.slot_action("set", "S2", {"model": "kisti/kistillm"}, "웹(test)", self.root)
        self.assertEqual(code, 200)
        self.assertEqual(body["slot"]["model"], "kisti/kistillm")
        code, body = server.slot_action("set", "S2", {"model": ""}, "웹(test)", self.root)   # 빈 값 = 하네스 기본
        self.assertEqual((code, body["slot"]["model"]), (200, None))
        code, body = server.slot_action("remove", "S2", {}, "웹(test)", self.root)
        self.assertEqual(code, 200)
        self.assertEqual([s["slot"] for s in aimem_db.slot_list()], ["S1"])
        titles = [__import__("json").loads(f.read_text(encoding="utf-8"))["title"] for f in (self.root / ".aimem" / "requests").glob("*.json")]
        self.assertTrue(any("S2 삭제됨" in t for t in titles))
        self.assertTrue(any("S2 변경됨" in t for t in titles))

    def test_model_must_be_configured_and_fit_harness(self):
        code, body = server.slot_action("add", None, {"harness": "claude", "model": "openai/gpt-9"}, "웹", self.root)
        self.assertEqual(code, 400)
        self.assertIn("설정된 모델이 아닙니다", body["error"])
        code, body = server.slot_action("add", None, {"harness": "codex", "model": "anthropic/claude-opus-5-5"}, "웹", self.root)
        self.assertEqual(code, 400)
        self.assertIn("받을 수 없습니다", body["error"])
        code, body = server.slot_action("add", None, {"harness": "claude", "model": "sonnet"}, "웹", self.root)   # CLI 별칭은 통과
        self.assertEqual(code, 201)

    def test_guards(self):
        self.assertEqual(server.slot_action("add", None, {"harness": "gemini"}, "웹", self.root)[0], 400)
        self.assertEqual(server.slot_action("set", "S9", {"model": "sonnet"}, "웹", self.root)[0], 404)
        self.assertEqual(server.slot_action("remove", "S9", {}, "웹", self.root)[0], 404)
        self.assertEqual(server.slot_action("add", None, "not-a-dict", "웹", self.root)[0], 400)
        other = pathlib.Path(self.tmp.name) / "elsewhere"
        other.mkdir()
        self.assertEqual(server.slot_action("add", None, {"harness": "claude"}, "웹", other)[0], 403)   # 운영 저장소 밖
        server.slot_action("add", "S1", {"harness": "claude"}, "웹", self.root)
        with mock.patch.object(server, "_slot_running", lambda slot, root: "T-1-S1-a1-000000"):
            self.assertEqual(server.slot_action("remove", "S1", {}, "웹", self.root)[0], 409)
            self.assertEqual(server.slot_action("set", "S1", {"harness": "codex"}, "웹", self.root)[0], 409)
            self.assertEqual(server.slot_action("set", "S1", {"role": "바꿈"}, "웹", self.root)[0], 400)   # 역할은 웹에서 못 바꾼다
            self.assertEqual(server.slot_action("set", "S1", {"model": "sonnet"}, "웹", self.root)[0], 200)  # 모델은 도는 중에도

    def test_models_for_harness_mapping(self):
        self.assertEqual(server._models_for_harness("anthropic/claude-opus-5-5"), ["claude"])
        self.assertEqual(server._models_for_harness("kisti/kistillm"), ["codex", "opencode"])
        self.assertEqual(server._models_for_harness("exaone/k-exaone_v2.5"), ["codex", "opencode"])


class OpenclawConfigModelsTest(unittest.TestCase):
    def test_reads_providers_and_default(self):
        import json as _json, tempfile as _tf
        with _tf.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "openclaw.json"
            p.write_text(_json.dumps({"models": {"providers": {"exaone": {"baseUrl": "x", "apiKey": "SECRET", "models": [{"id": "k-exaone_v2.5", "name": "EXAONE"}]},
                                                                  "kisti": {"models": [{"id": "kistillm"}]}}},
                                      "agents": {"defaults": {"model": {"primary": "exaone/k-exaone_v2.5"}}}}), encoding="utf-8")
            out = server._models_from_openclaw_config(p)
        self.assertEqual(out["exaone/k-exaone_v2.5"], {"name": "EXAONE", "default": True})
        self.assertEqual(out["kisti/kistillm"], {"name": "kistillm"})
        self.assertNotIn("SECRET", _json.dumps(out))


class FleetModelNormalizeTest(unittest.TestCase):
    def test_normalize(self):
        import fleet
        self.assertEqual(fleet.normalize_model("claude", "anthropic/claude-opus-5-5"), "claude-opus-5-5")
        self.assertEqual(fleet.normalize_model("claude", "opus"), "opus")
        self.assertEqual(fleet.normalize_model("opencode", "exaone/k-exaone_v2.5"), "exaone/k-exaone_v2.5")
        self.assertIsNone(fleet.normalize_model("codex", None))
        argv, _ = fleet._worker_argv("codex", "kisti/kistillm", "/tmp/b.md")
        self.assertIn("-m", argv)
        self.assertEqual(argv[argv.index("-m") + 1], "kistillm")
        self.assertIn("model_provider=kisti", argv)
        argv, _ = fleet._worker_argv("claude", "anthropic/claude-opus-5-5", "/tmp/b.md")
        self.assertEqual(argv[argv.index("--model") + 1], "claude-opus-5-5")


if __name__ == "__main__":
    unittest.main()


class ArchiveActionTest(SlotActionTest):
    def test_archive_action_dry_run_and_apply(self):
        rdir = self.root / ".aimem" / "requests"; rdir.mkdir(exist_ok=True)
        (rdir / "Q-9.json").write_text('{"id":"Q-9","status":"DONE","title":"t","created":"2026-01-01 10:00","updated":"2026-01-02 10:00"}', encoding="utf-8")
        code, body = server.archive_action({"days": 14, "dry_run": True}, "웹", self.root)
        self.assertEqual(code, 200)
        self.assertTrue(body["dry_run"])
        self.assertEqual([r["id"] for r in body["plan"]["requests"]], ["Q-9"])
        self.assertTrue((rdir / "Q-9.json").exists())
        code, body = server.archive_action({"days": 14}, "웹", self.root)
        self.assertEqual(code, 200)
        self.assertEqual(body["moved"]["requests"], ["Q-9"])
        self.assertFalse((rdir / "Q-9.json").exists())
        self.assertEqual(server.archive_action({"days": "x"}, "웹", self.root)[0], 400)
        self.assertEqual(server.archive_action({"days": True}, "웹", self.root)[0], 400)
