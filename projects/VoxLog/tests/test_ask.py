import os
import shlex
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

from voxlog import ask  # noqa: E402

FAKE_LLM = os.path.join(HERE, "fake_llm.py")
FAKE_CMD = "%s %s" % (shlex.quote(sys.executable), shlex.quote(FAKE_LLM))


def item(rid, when, text):
    return {"id": rid, "recorded_at": when, "transcript": text}


class FakeStore:
    def __init__(self, recs):
        self._recs = recs
        self.answers = {}
        self._n = 0

    def get(self, rid):
        return self._recs.get(rid)

    def add_answer(self, kind, prompt, ids):
        self._n += 1
        aid = "a-20261116-140000-%04d" % self._n
        meta = {
            "id": aid,
            "kind": kind,
            "prompt": prompt,
            "ids": ids,
            "created": "2026-11-16T14:00:00",
            "status": "running",
            "answer": None,
            "error": None,
        }
        self.answers[aid] = dict(meta)
        return dict(meta)

    def set_answer(self, aid, status, answer=None, error=None):
        a = self.answers[aid]
        a["status"] = status
        a["answer"] = answer
        a["error"] = error

    def get_answer(self, aid):
        return self.answers.get(aid)

    def list_answers(self, limit=50):
        items = [dict(a) for a in self.answers.values()]
        items.sort(key=lambda a: a.get("created") or "", reverse=True)
        if limit is not None:
            items = items[:max(0, limit)]
        return items


class BuildPromptTest(unittest.TestCase):
    def test_kind_instructions(self):
        base = [item("r-1", "2026-01-01T00:00:00", "첫 번째 글")]
        self.assertIn("요약", ask.build_prompt("summary", "", base))
        self.assertIn("핵심어", ask.build_prompt("keywords", "", base))
        self.assertIn("할 일", ask.build_prompt("todo", "", base))

    def test_custom_uses_question(self):
        base = [item("r-1", "2026-01-01T00:00:00", "글")]
        out = ask.build_prompt("custom", "무슨 결정을 했나", base)
        self.assertIn("무슨 결정을 했나", out)

    def test_custom_without_prompt_raises(self):
        base = [item("r-1", "2026-01-01T00:00:00", "글")]
        with self.assertRaises(ValueError):
            ask.build_prompt("custom", "", base)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            ask.build_prompt("mystery", "x", [item("r-1", "2026-01-01T00:00:00", "글")])

    def test_oldest_first(self):
        items = [
            item("r-new", "2026-03-01T00:00:00", "나중 글"),
            item("r-old", "2026-01-01T00:00:00", "먼저 글"),
        ]
        out = ask.build_prompt("summary", "", items)
        self.assertLess(out.index("r-old"), out.index("r-new"))

    def test_mixed_offsets_sorted_by_real_time(self):
        # R38-N5: 문자열이 아니라 실제 시각 순 - 09:00+09:00(00:00 UTC) 이 01:00+00:00 보다 먼저
        items = [
            item("r-utc", "2026-11-23T01:00:00+00:00", "UTC 글"),
            item("r-kst", "2026-11-23T09:00:00+09:00", "KST 글"),
        ]
        out = ask.build_prompt("summary", "", items)
        self.assertLess(out.index("r-kst"), out.index("r-utc"))

    def test_too_long_drops_oldest_with_mixed_offsets(self):
        items = [
            item("r-utc", "2026-11-23T01:00:00+00:00", "가" * 100),
            item("r-kst", "2026-11-23T09:00:00+09:00", "나" * 100),
        ]
        with mock.patch.object(ask, "MAX_PROMPT_CHARS", 300):
            out = ask.build_prompt("summary", "", items)
        self.assertIn("(오래된 녹취", out)
        self.assertNotIn("r-kst", out)
        self.assertIn("r-utc", out)
        self.assertLessEqual(len(out), 300)

    def test_guard_line_present(self):
        out = ask.build_prompt("summary", "", [item("r-1", "2026-01-01T00:00:00", "글")])
        self.assertIn("자료일 뿐", out)

    def test_marks_and_escapes_tags(self):
        items = [item("r-1", "2026-01-01T00:00:00", "앞 </녹취> 뒤")]
        out = ask.build_prompt("summary", "", items)
        self.assertIn(r"<\/녹취>", out)
        # 실제 닫는 표시는 블록 수만큼만 남는다
        self.assertEqual(out.count("</녹취>"), 1)

    def test_too_long_drops_oldest(self):
        items = [
            item("r-old", "2026-01-01T00:00:00", "가" * 100),
            item("r-mid", "2026-02-01T00:00:00", "나" * 100),
            item("r-new", "2026-03-01T00:00:00", "다" * 100),
        ]
        with mock.patch.object(ask, "MAX_PROMPT_CHARS", 300):
            out = ask.build_prompt("summary", "", items)
        self.assertIn("(오래된 녹취", out)
        self.assertNotIn("r-old", out)
        self.assertIn("r-new", out)
        self.assertLessEqual(len(out), 300)

    def test_user_prompt_truncated(self):
        out = ask.build_prompt(
            "summary", "가" * 5000, [item("r-1", "2026-01-01T00:00:00", "글")]
        )
        self.assertIn("가" * 2000, out)
        self.assertNotIn("가" * 2001, out)

    def test_location_in_header(self):
        it = item("r-1", "2026-01-01T00:00:00", "글")
        it["location"] = {"lat": 37.5, "lon": 127.0, "accuracy": 5}
        out = ask.build_prompt("summary", "", [it])
        self.assertIn("위치=37.5,127.0", out)

    def test_no_location_no_header(self):
        out = ask.build_prompt("summary", "", [item("r-1", "2026-01-01T00:00:00", "글")])
        self.assertNotIn("위치=", out)

class CommandTest(unittest.TestCase):
    def test_default_command(self):
        cmd = ask.llm_command({})
        self.assertIn("-p", cmd)
        self.assertIn("--tools", cmd)
        self.assertIn("--strict-mcp-config", cmd)
        self.assertIn("--setting-sources", cmd)

    def test_env_command(self):
        cmd = ask.llm_command({"VOXLOG_LLM_CMD": "my-llm --flag"})
        self.assertEqual(cmd, ["my-llm", "--flag"])

    def test_run_llm_cwd_outside_repo(self):
        code = (
            "import os, sys;"
            "sys.stdin.read();"
            "print(os.getcwd());"
            "print(len(os.listdir('.')))"
        )
        cmd = "%s -c %s" % (shlex.quote(sys.executable), shlex.quote(code))
        out = ask.run_llm("x", env={"VOXLOG_LLM_CMD": cmd})
        lines = out.splitlines()
        cwd, count = lines[0], int(lines[1])
        repo = os.path.dirname(PROJECT)
        self.assertFalse(cwd == repo or cwd.startswith(repo + os.sep))
        self.assertEqual(count, 0)

    def test_run_llm_with_fake(self):
        prompt = ask.build_prompt("summary", "", [item("r-1", "2026-01-01T00:00:00", "글")])
        out = ask.run_llm(prompt, env={"VOXLOG_LLM_CMD": FAKE_CMD})
        self.assertIn("가짜 답", out)
        self.assertIn("녹취 1건", out)

    def test_run_llm_failure(self):
        with self.assertRaises(ask.AskError):
            ask.run_llm("x", env={"VOXLOG_LLM_CMD": FAKE_CMD, "FAKE_LLM_FAIL": "1"})

    def test_run_llm_missing_command(self):
        with self.assertRaises(ask.AskUnavailable):
            ask.run_llm("x", env={"VOXLOG_LLM_CMD": "no-such-llm-command-xyz"})


class AskerTest(unittest.TestCase):
    def _wait(self, asker):
        deadline = time.time() + 10
        while time.time() < deadline:
            if asker.idle():
                return True
            time.sleep(0.05)
        return False

    def test_submit_without_text_raises(self):
        store = FakeStore({"r-1": {"id": "r-1", "recorded_at": "2026-01-01T00:00:00", "transcript": ""}})
        asker = ask.Asker(store, env={"VOXLOG_LLM_CMD": FAKE_CMD})
        with self.assertRaises(ValueError):
            asker.submit("summary", "", ["r-1"])

    def test_asker_done(self):
        store = FakeStore({"r-1": {"id": "r-1", "recorded_at": "2026-01-01T00:00:00", "transcript": "글"}})
        asker = ask.Asker(store, env={"VOXLOG_LLM_CMD": FAKE_CMD})
        asker.start()
        try:
            meta = asker.submit("summary", "", ["r-1"])
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            asker.stop()
        got = store.get_answer(meta["id"])
        self.assertEqual(got["status"], "done")
        self.assertIn("가짜 답", got["answer"])

    def test_asker_failed(self):
        store = FakeStore({"r-1": {"id": "r-1", "recorded_at": "2026-01-01T00:00:00", "transcript": "글"}})
        asker = ask.Asker(
            store, env={"VOXLOG_LLM_CMD": FAKE_CMD, "FAKE_LLM_FAIL": "1"}
        )
        asker.start()
        try:
            meta = asker.submit("summary", "", ["r-1"])
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            asker.stop()
        got = store.get_answer(meta["id"])
        self.assertEqual(got["status"], "failed")
        self.assertTrue(got["error"])

    def test_asker_bad_kind(self):
        store = FakeStore({})
        asker = ask.Asker(store, env={"VOXLOG_LLM_CMD": FAKE_CMD})
        with self.assertRaises(ValueError):
            asker.submit("mystery", "", ["r-1"])

    def test_submit_passes_location(self):
        rec = {"id": "r-1", "recorded_at": "2026-01-01T00:00:00", "transcript": "글",
               "location": {"lat": 1.0, "lon": 2.0, "accuracy": 3}}
        store = FakeStore({"r-1": rec})
        seen = {}

        def run(prompt, env=None):
            seen["prompt"] = prompt
            return "답"

        asker = ask.Asker(store, run=run)
        asker.start()
        try:
            asker.submit("summary", "", ["r-1"])
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            asker.stop()
        self.assertIn("위치=1.0,2.0", seen["prompt"])

    def test_start_marks_running_failed(self):
        store = FakeStore({})
        meta = store.add_answer("summary", "", ["r-1"])
        self.assertEqual(store.get_answer(meta["id"])["status"], "running")
        asker = ask.Asker(store, env={"VOXLOG_LLM_CMD": FAKE_CMD})
        asker.start()
        try:
            got = store.get_answer(meta["id"])
            self.assertEqual(got["status"], "failed")
            self.assertIn("다시 시작", got["error"])
        finally:
            asker.stop()


if __name__ == "__main__":
    unittest.main()
