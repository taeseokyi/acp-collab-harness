import _fleet_env  # noqa: F401
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from fleet_rt.base import SessionSpec
from fleet_rt.harness import claude as claude_h

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "harness" / "claude_ok.jsonl"
REPO = pathlib.Path(__file__).resolve().parent.parent


def _spec(cwd=str(REPO), **kw):
    base = dict(id="T-1-S1-a1-000000", role="worker", harness="claude", brief_path="/x/brief.md", cwd=cwd)
    base.update(kw)
    return SessionSpec(**base)


def _session_dir(tmp, lines, stderr=None):
    d = pathlib.Path(tmp)
    (d / "events.jsonl").write_text(
        "".join(f"2026-11-12T10:00:00\t{ln}\n" for ln in lines), encoding="utf-8")
    if stderr is not None:
        (d / "stderr.log").write_text(stderr, encoding="utf-8")
    return d


def _result(**kw):
    d = {"type": "result", "subtype": "success", "is_error": False, "result": "OK", "session_id": "s1"}
    d.update(kw)
    return json.dumps(d)


class CommandTest(unittest.TestCase):
    def test_worker_argv(self):
        c = claude_h.ADAPTER.command(_spec(model="anthropic/opus"))
        self.assertEqual(c.argv, ["claude", "-p", "--model", "opus", "--output-format", "stream-json", "--verbose",
                                  "--permission-mode", "acceptEdits", "--allowedTools", claude_h.WORKER_TOOLS])
        self.assertEqual(c.stdin_path, "/x/brief.md")
        self.assertEqual(c.cwd, str(REPO))
        self.assertEqual(c.env_unset, claude_h.NESTED_ENV)
        self.assertIn("CLAUDECODE", c.env_unset)

    def test_default_model_tools_settings(self):
        c = claude_h.ADAPTER.command(_spec(tools="Read,Grep", settings_path="/s.json"))
        self.assertEqual(c.argv[3], "sonnet")
        self.assertEqual(c.argv[c.argv.index("--allowedTools") + 1], "Read,Grep")
        self.assertEqual(c.argv[-2:], ["--settings", "/s.json"])
        self.assertNotIn("--session-id", c.argv)

    def test_manager_session_id(self):
        c = claude_h.ADAPTER.command(_spec(role="manager", model="opus",
                                           extra={"harness_session_id": "abc-123"}))
        self.assertEqual(c.argv[-2:], ["--session-id", "abc-123"])

    def test_resume(self):
        c = claude_h.ADAPTER.resume_command(_spec(role="manager", model="opus",
                                                  extra={"harness_session_id": "zzz"}), "abc", "/x/msg.md")
        self.assertEqual(c.argv[-2:], ["--resume", "abc"])
        self.assertNotIn("--session-id", c.argv)
        self.assertEqual(c.stdin_path, "/x/msg.md")

    def test_cwd_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                claude_h.ADAPTER.command(_spec(cwd=tmp))
            with self.assertRaises(ValueError):
                claude_h._require_repo_cwd(tmp + "/nope")
            (pathlib.Path(tmp) / "tools").mkdir()
            (pathlib.Path(tmp) / "tools" / "fleet.py").write_text("")
            claude_h._require_repo_cwd(tmp)
            self.assertEqual(claude_h.ADAPTER.command(_spec(cwd=tmp)).cwd, tmp)


class ParseTest(unittest.TestCase):
    def test_fixture_lines(self):
        events = [claude_h.ADAPTER.parse_event(ln) for ln in FIXTURE.read_text().splitlines()]
        kinds = [e.kind for e in events if e]
        tool = next(e for e in events if e and e.kind == "tool")
        self.assertEqual(tool.text, "Bash: echo fleet-sample")
        self.assertEqual(tool.data["name"], "Bash")
        self.assertEqual(tool.data["input"]["command"], "echo fleet-sample")
        self.assertTrue(any(e.kind == "text" and e.text == "DONE" for e in events if e))
        end = [e for e in events if e and e.kind == "end"]
        self.assertEqual(len(end), 1)
        self.assertIs(end[0].data["ok"], True)
        self.assertEqual(end[0].data["result"], "DONE")
        self.assertEqual(end[0].data["harness_session_id"], "8b184ed4-f186-4cca-8087-2f3dfaaf588c")
        self.assertEqual(end[0].data["tokens_out"], 149)
        self.assertIn("usage", kinds)
        init = events[0]
        self.assertEqual(init.kind, "raw")
        self.assertEqual(init.data["harness_session_id"], "8b184ed4-f186-4cca-8087-2f3dfaaf588c")

    def test_thinking_skipped(self):
        ln = json.dumps({"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": ""}]}})
        self.assertIsNone(claude_h.ADAPTER.parse_event(ln))

    def test_tool_preferred_over_text(self):
        ln = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "hi"},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/a/" + "b" * 300}}]}})
        e = claude_h.ADAPTER.parse_event(ln)
        self.assertEqual(e.kind, "tool")
        self.assertLessEqual(len(e.text), 130)

    def test_rate_limit_rejected(self):
        ln = json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}})
        e = claude_h.ADAPTER.parse_event(ln)
        self.assertEqual(e.kind, "error")
        self.assertIs(e.data["limit"], True)

    def test_non_json_and_blank(self):
        e = claude_h.ADAPTER.parse_event("not json {")
        self.assertEqual((e.kind, e.raw), ("raw", "not json {"))
        self.assertIsNone(claude_h.ADAPTER.parse_event("   "))
        self.assertEqual(claude_h.ADAPTER.parse_event('{"type":"mystery"}').kind, "raw")


class ReportTest(unittest.TestCase):
    def test_final_report_from_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _session_dir(tmp, FIXTURE.read_text().splitlines())
            self.assertEqual(claude_h.ADAPTER.final_report(d), "DONE")
            self.assertIs(claude_h.ADAPTER.limit_signal(d), False)

    def test_final_report_without_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = [json.dumps({"type": "assistant", "message": {"id": "m1", "content": [
                {"type": "text", "text": "중간 보고"}]}})]
            self.assertEqual(claude_h.ADAPTER.final_report(_session_dir(tmp, lines)), "중간 보고")

    def test_final_report_stderr_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _session_dir(tmp, [], stderr="\x1b[31mboom\x1b[0m\n$ noise\nreal error\n")
            rep = claude_h.ADAPTER.final_report(d)
            self.assertTrue(rep.startswith("(최종 보고문 없음"))
            self.assertIn("real error", rep)
            self.assertNotIn("noise", rep)
            self.assertNotIn("\x1b", rep)

    def test_final_report_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(claude_h.ADAPTER.final_report(_session_dir(tmp, [])), "")


class LimitTest(unittest.TestCase):
    def _sig(self, lines):
        with tempfile.TemporaryDirectory() as tmp:
            return claude_h.ADAPTER.limit_signal(_session_dir(tmp, lines))

    def test_none_without_result(self):
        self.assertIsNone(self._sig([]))
        self.assertIsNone(self._sig(['{"type":"assistant"}']))

    def test_false_on_success(self):
        self.assertIs(self._sig([_result()]), False)

    def test_429(self):
        self.assertIs(self._sig([_result(is_error=True, api_error_status=429)]), True)

    def test_api_error_text(self):
        self.assertIs(self._sig([_result(is_error=True, api_error="usage_limit_exceeded")]), True)
        self.assertIs(self._sig([_result(is_error=True, terminal_reason="api_error",
                                         result="You've hit your limit")]), True)

    def test_other_error_false(self):
        self.assertIs(self._sig([_result(is_error=True, api_error_status=500, result="boom")]), False)

    def test_rejected_event_then_error(self):
        ev = json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}})
        self.assertIs(self._sig([ev, _result(is_error=True, result="stopped")]), True)
        # 성공으로 끝났다면 거절 신호가 있어도 한도 실패가 아니다
        self.assertIs(self._sig([ev, _result()]), False)


class ProbeTest(unittest.TestCase):
    def test_missing(self):
        with mock.patch.object(claude_h.shutil, "which", return_value=None):
            self.assertFalse(claude_h.ADAPTER.probe().ok)

    def test_ok(self):
        cp = mock.Mock(returncode=0, stdout="2.1.322 (Claude Code)\n")
        with mock.patch.object(claude_h.shutil, "which", return_value="/bin/claude"), \
                mock.patch.object(claude_h.subprocess, "run", return_value=cp) as run:
            r = claude_h.ADAPTER.probe()
        self.assertTrue(r.ok)
        self.assertEqual(r.version, "2.1.322 (Claude Code)")
        self.assertEqual(run.call_args[0][0], ["/bin/claude", "--version"])


if __name__ == "__main__":
    unittest.main()
