"""슬롯 관리 API 계약 (2026-11-10, 태석님 지시 "슬롯 하네스 추가·삭제 + 모델 지정").

`server.slot_action` 은 DB(`aimem_db`)를 고치고, 모델은 `fleet.toml` 에 설정된 목록에서만 받는다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fleet_env  # noqa: F401,E402 - 세션 표식을 걷는다 (관리자 세션 안에서 돌려도 같은 결과)

import contextlib
import io
import json
import pathlib
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
                                    (server, "ROOT", self.root), (server, "fleet_models", lambda *a, **k: MODELS),
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
        self.assertIn("fleet.toml 에 설정된 모델이 아닙니다", body["error"])
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

    def test_claude_ids_and_aliases_pass_without_the_list(self):
        for m in ("opus", "sonnet", "haiku", "claude-opus-5-5", "anthropic/claude-opus-5-5"):
            self.assertEqual(server._model_allowed(m, "claude", self.root), (True, ""), m)
        self.assertFalse(server._model_allowed("opus", "codex", self.root)[0])   # 별칭 예외는 claude 하네스만


class FleetTomlModelsTest(unittest.TestCase):
    """`/api/models` 의 원천 - 임시 저장소의 `fleet.toml` (비밀 키는 읽지 않는다)."""

    def test_reads_providers_per_harness(self):
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "fleet.toml").write_text(
                '[providers.kisti]\nenv_key = "KISTI_API_KEY"\nmodels = ["kistillm"]\n'
                '[providers.anthropic]\nmodels = ["opus", "sonnet"]\n'
                '[harness.claude]\nproviders = ["anthropic"]\n'
                '[harness.codex]\nproviders = ["kisti"]\n[harness.opencode]\nproviders = ["kisti"]\n', encoding="utf-8")
            out = server.fleet_models(pathlib.Path(d))
        self.assertTrue(out["ok"])
        by = {m["key"]: m for m in out["models"]}
        self.assertEqual(sorted(by), ["kisti/kistillm", "opus", "sonnet"])
        self.assertEqual(by["kisti/kistillm"]["harnesses"], ["codex", "opencode"])
        self.assertEqual(by["opus"]["harnesses"], ["claude"])
        self.assertEqual(out["models"][0]["provider"], "anthropic")     # anthropic 이 앞
        self.assertNotIn("openclaw", json.dumps(out))

    def test_broken_file_degrades_to_error(self):
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "fleet.toml").write_text("[providers\n", encoding="utf-8")
            out = server.fleet_models(pathlib.Path(d))
        self.assertFalse(out["ok"])
        self.assertEqual(out["models"], [])
        self.assertIn("ConfigError", out["error"])


class FleetModelNormalizeTest(unittest.TestCase):
    def test_normalize(self):
        import fleet
        self.assertEqual(fleet.normalize_model("claude", "anthropic/claude-opus-5-5"), "claude-opus-5-5")
        self.assertEqual(fleet.normalize_model("claude", "opus"), "opus")
        self.assertEqual(fleet.normalize_model("opencode", "exaone/k-exaone_v2.5"), "exaone/k-exaone_v2.5")
        self.assertIsNone(fleet.normalize_model("codex", None))
        # 하네스별 명령 꼴은 어댑터 검사(tests/test_rt_codex.py · test_rt_opencode.py · test_rt_claude.py)가 본다


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
