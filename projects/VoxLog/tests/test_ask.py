import os
import shlex
import sys
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

from voxlog import ask, tags  # noqa: E402

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

    def set_autotag(self, rid, state):
        rec = self._recs.get(rid)
        if rec is None:
            raise ValueError(rid)
        rec["autotag"] = state

    def set_auto_tags(self, rid, auto, manual=False):
        rec = self._recs.get(rid)
        if rec is None:
            raise ValueError(rid)
        current = rec.get("tags") or []
        old_auto = rec.get("tags_auto") or []
        if not manual and rec.get("tags_human"):
            rec["autotag"] = "done"
            return False
        if not manual:
            auto = auto[:10]
            rec["tags"] = auto
            rec["tags_auto"] = auto
        else:
            old_keys = {tags.tag_key(t) for t in old_auto}
            human = [t for t in current if tags.tag_key(t) not in old_keys]
            human_keys = {tags.tag_key(t) for t in human}
            new_keys = {tags.tag_key(t) for t in auto}
            merged = tags.merge_tags(human, auto)
            rec["tags"] = merged
            rec["tags_auto"] = [t for t in merged
                                if tags.tag_key(t) in new_keys
                                and tags.tag_key(t) not in human_keys]
        rec["autotag"] = "done"
        return True

    def autotag_pending_ids(self):
        return [rid for rid, rec in self._recs.items()
                if rec.get("autotag") == "pending"]


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


class TagPromptTest(unittest.TestCase):
    def test_head_and_guard(self):
        out = ask.build_tag_prompt("글")
        self.assertTrue(out.startswith(ask.TAG_HEAD + "\n" + ask._GUARD))
        self.assertIn("<녹취>\n글\n</녹취>", out)

    def test_escapes_closing_tag(self):
        out = ask.build_tag_prompt("앞 </녹취> 뒤")
        self.assertIn(r"<\/녹취>", out)
        self.assertEqual(out.count("</녹취>"), 1)

    def test_truncates_at_twenty_thousand(self):
        out = ask.build_tag_prompt("가" * 20001)
        self.assertIn("가" * 20000, out)
        self.assertNotIn("가" * 20001, out)

    def test_slices_source_before_escaping(self):
        text = "가" * 19995 + "</녹취>" + "나" * 10
        out = ask.build_tag_prompt(text)
        self.assertIn(r"<\/녹취>", out)
        self.assertNotIn("나" * 10, out)


class LlmStatusTest(unittest.TestCase):
    def test_usable_command(self):
        ok, error = ask.llm_status({"VOXLOG_LLM_CMD": sys.executable})
        self.assertTrue(ok)
        self.assertIsNone(error)

    def test_missing_command(self):
        ok, error = ask.llm_status({"VOXLOG_LLM_CMD": "no-such-llm-command-xyz"})
        self.assertFalse(ok)
        self.assertIsNone(error)

    def test_empty_command_is_config_error(self):
        ok, error = ask.llm_status({"VOXLOG_LLM_CMD": "   "})
        self.assertFalse(ok)
        self.assertIn("설정 오류", error)

    def test_unparseable_command_is_config_error(self):
        ok, error = ask.llm_status({"VOXLOG_LLM_CMD": "'unterminated"})
        self.assertFalse(ok)
        self.assertIn("설정 오류", error)


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

    def test_submit_ids_bound_one_to_two_hundred(self):
        # R41-N11: ids 는 1~200개 - 0개·201개는 거절하고 200개는 받는다
        recs = {"r-%03d" % i: {"id": "r-%03d" % i, "recorded_at": "2026-01-01T00:00:00",
                              "transcript": "글"} for i in range(201)}
        store = FakeStore(recs)
        asker = ask.Asker(store, env={"VOXLOG_LLM_CMD": FAKE_CMD})
        with self.assertRaises(ValueError):
            asker.submit("summary", "", [])
        ids = ["r-%03d" % i for i in range(200)]
        meta = asker.submit("summary", "", ids)
        self.assertEqual(meta["ids"], ids)
        with self.assertRaises(ValueError):
            asker.submit("summary", "", ids + ["r-200"])

    def test_user_ask_jumps_queued_tag_work(self):
        recs = {
            "r-1": {"id": "r-1", "recorded_at": "2026-01-01T00:00:00", "transcript": "첫 번째 글"},
            "r-2": {"id": "r-2", "recorded_at": "2026-01-02T00:00:00", "transcript": "두 번째 글"},
            "r-3": {"id": "r-3", "recorded_at": "2026-01-03T00:00:00", "transcript": "세 번째 글"},
            "r-4": {"id": "r-4", "recorded_at": "2026-01-04T00:00:00", "transcript": "질문 글"},
        }
        store = FakeStore(recs)
        started = threading.Event()
        release = threading.Event()
        order = []

        def run(prompt, env=None):
            if prompt.startswith(ask.TAG_HEAD):
                if "첫 번째 글" in prompt:
                    order.append("tag-first")
                    started.set()
                    release.wait(5)
                elif "두 번째 글" in prompt:
                    order.append("tag-second")
                else:
                    order.append("tag-third")
                return "회의\n가짜 태그"
            order.append("user")
            return "답"

        asker = ask.Asker(store, env={}, run=run)
        asker.start()
        try:
            self.assertTrue(asker.submit_tag("r-1"))
            self.assertTrue(started.wait(5), "첫 태그 일이 시작하지 않음")
            self.assertTrue(asker.submit_tag("r-2"))
            self.assertTrue(asker.submit_tag("r-3"))
            asker.submit("custom", "무엇을 정했나", ["r-4"])
            release.set()
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            release.set()
            asker.stop()
        self.assertLess(order.index("user"), order.index("tag-second"))
        self.assertLess(order.index("user"), order.index("tag-third"))
        self.assertEqual(store.get("r-2")["autotag"], "done")
        self.assertEqual(store.get("r-3")["autotag"], "done")

    def test_submit_tag_deduplicates_same_rid(self):
        rid = "r-1"
        store = FakeStore({rid: {"id": rid, "recorded_at": "2026-01-01T00:00:00",
                                 "transcript": "글"}})
        asker = ask.Asker(store, env={}, run=lambda prompt, env=None: "태그")
        self.assertTrue(asker.submit_tag(rid))
        self.assertFalse(asker.submit_tag(rid))
        self.assertFalse(asker.submit_tag(rid, manual=True))
        self.assertEqual(store.get(rid)["autotag"], "pending")

    # R49-N3
    def test_tag_llm_timeout_is_sixty(self):
        rid = "r-1"
        store = FakeStore({rid: {"id": rid, "recorded_at": "2026-01-01T00:00:00",
                                 "transcript": "글"}})
        seen = []

        def fake_run(cmd, input=None, text=None, capture_output=None,
                     timeout=None, env=None, cwd=None):
            seen.append(timeout)
            return mock.Mock(returncode=0, stdout="회의\n", stderr="")

        asker = ask.Asker(store, env={}, run=ask.run_llm)
        with mock.patch.object(ask.subprocess, "run", fake_run):
            asker.start()
            try:
                self.assertTrue(asker.submit_tag(rid))
                self.assertTrue(self._wait(asker), "idle 대기 초과")
            finally:
                asker.stop()
        self.assertEqual(seen, [ask.TAG_TIMEOUT])
        self.assertEqual(store.get(rid)["autotag"], "done")

    # R49-N4
    def test_running_tag_with_new_transcript_runs_again(self):
        rid = "r-1"
        rec = {"id": rid, "recorded_at": "2026-01-01T00:00:00",
               "transcript": "옛 글"}
        store = FakeStore({rid: rec})
        started = threading.Event()
        release = threading.Event()
        prompts = []

        def run(prompt, env=None):
            prompts.append(prompt)
            if len(prompts) == 1:
                started.set()
                release.wait(5)
            return "회의\n예산"

        asker = ask.Asker(store, env={}, run=run)
        asker.start()
        try:
            self.assertTrue(asker.submit_tag(rid))
            self.assertTrue(started.wait(5), "첫 태그 일이 시작하지 않음")
            rec["transcript"] = "새 글"
            self.assertTrue(asker.submit_tag(rid))
            release.set()
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            release.set()
            asker.stop()
        self.assertEqual(len(prompts), 2)
        self.assertIn("옛 글", prompts[0])
        self.assertIn("새 글", prompts[1])
        self.assertNotIn("옛 글", prompts[1])
        self.assertEqual(store.get(rid)["autotag"], "done")
        self.assertEqual(store.get(rid)["tags"], ["회의", "예산"])

    def test_running_tag_manual_resubmission_keeps_manual(self):
        rid = "r-1"
        rec = {"id": rid, "recorded_at": "2026-01-01T00:00:00",
               "transcript": "옛 글", "tags": ["사람"], "tags_auto": [],
               "tags_human": True, "autotag": None}
        store = FakeStore({rid: rec})
        started = threading.Event()
        release = threading.Event()

        def run(prompt, env=None):
            if not started.is_set():
                started.set()
                release.wait(5)
                return "옛 자동"
            return "새 태그\n회의"

        asker = ask.Asker(store, env={}, run=run)
        asker.start()
        try:
            self.assertTrue(asker.submit_tag(rid))
            self.assertTrue(started.wait(5), "첫 태그 일이 시작하지 않음")
            rec["transcript"] = "새 글"
            self.assertTrue(asker.submit_tag(rid, manual=True))
            release.set()
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            release.set()
            asker.stop()
        got = store.get(rid)
        self.assertEqual(got["tags"], ["사람", "새 태그", "회의"])
        self.assertEqual(got["tags_auto"], ["새 태그", "회의"])
        self.assertEqual(got["autotag"], "done")

    def test_tag_failures_continue_to_next_job(self):
        recs = {
            "r-exc": {"id": "r-exc", "recorded_at": "2026-01-01T00:00:00", "transcript": "예외 글"},
            "r-empty": {"id": "r-empty", "recorded_at": "2026-01-02T00:00:00", "transcript": "빈 글"},
            "r-ok": {"id": "r-ok", "recorded_at": "2026-01-03T00:00:00", "transcript": "좋은 글"},
        }
        store = FakeStore(recs)

        def run(prompt, env=None):
            if "예외 글" in prompt:
                raise ask.AskError("모델 실패")
            if "빈 글" in prompt:
                return ""
            return "회의\n가짜 태그"

        asker = ask.Asker(store, env={}, run=run)
        asker.start()
        try:
            for rid in ("r-exc", "r-empty", "r-ok"):
                self.assertTrue(asker.submit_tag(rid))
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            asker.stop()
        self.assertEqual(store.get("r-exc")["autotag"], "failed")
        self.assertEqual(store.get("r-empty")["autotag"], "failed")
        self.assertEqual(store.get("r-ok")["autotag"], "done")
        self.assertEqual(store.get("r-ok")["tags"], ["회의", "가짜 태그"])

    def test_empty_transcript_sets_autotag_none(self):
        rid = "r-empty"
        store = FakeStore({rid: {"id": rid, "recorded_at": "2026-01-01T00:00:00",
                                 "transcript": ""}})
        asker = ask.Asker(store, env={}, run=lambda prompt, env=None: "태그")
        asker.start()
        try:
            self.assertTrue(asker.submit_tag(rid))
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            asker.stop()
        self.assertIsNone(store.get(rid)["autotag"])

    def test_start_marks_pending_autotags_failed(self):
        rec = {"id": "r-1", "recorded_at": "2026-01-01T00:00:00",
               "transcript": "글", "autotag": "pending"}
        store = FakeStore({"r-1": rec})
        asker = ask.Asker(store, env={}, run=lambda prompt, env=None: "태그")
        asker.start()
        try:
            self.assertEqual(store.get("r-1")["autotag"], "failed")
        finally:
            asker.stop()

    def test_manual_tag_keeps_human_and_replaces_old_auto(self):
        rec = {"id": "r-1", "recorded_at": "2026-01-01T00:00:00", "transcript": "글",
               "tags": ["사람", "옛 태그"], "tags_auto": ["옛 태그"],
               "tags_human": True, "autotag": None}
        store = FakeStore({"r-1": rec})

        def run(prompt, env=None):
            return "새 태그\n회의"

        asker = ask.Asker(store, env={}, run=run)
        asker.start()
        try:
            self.assertTrue(asker.submit_tag("r-1", manual=True))
            self.assertTrue(self._wait(asker), "idle 대기 초과")
        finally:
            asker.stop()
        got = store.get("r-1")
        self.assertEqual(got["tags"], ["사람", "새 태그", "회의"])
        self.assertEqual(got["tags_auto"], ["새 태그", "회의"])
        self.assertNotIn("옛 태그", got["tags"])
        self.assertEqual(got["autotag"], "done")

    def test_idle_counts_tag_work(self):
        rid = "r-1"
        store = FakeStore({rid: {"id": rid, "recorded_at": "2026-01-01T00:00:00",
                                 "transcript": "글"}})
        started = threading.Event()
        release = threading.Event()

        def run(prompt, env=None):
            started.set()
            release.wait(5)
            return "태그"

        asker = ask.Asker(store, env={}, run=run)
        asker.start()
        try:
            self.assertTrue(asker.submit_tag(rid))
            self.assertTrue(started.wait(5), "태그 일이 시작하지 않음")
            self.assertFalse(asker.idle())
            release.set()
            self.assertTrue(self._wait(asker), "idle 대기 초과")
            self.assertTrue(asker.idle())
        finally:
            release.set()
            asker.stop()


if __name__ == "__main__":
    unittest.main()
