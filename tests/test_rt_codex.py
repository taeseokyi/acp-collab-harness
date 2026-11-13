import _fleet_env  # noqa: F401
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from fleet_rt.base import SessionSpec
from fleet_rt.harness import codex as codex_h

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "harness"
A = codex_h.ADAPTER

# 손으로 쓴 줄이다 (실측 아님): 공급자 장애로 성공 표본이 없어 0.162.1 의 알려진 모양대로 지었다.
HAND = [
    '{"type":"thread.started","thread_id":"T1"}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"i0","type":"reasoning","text":"생각"}}',
    '{"type":"item.started","item":{"id":"i1","type":"command_execution","command":"ls tools","aggregated_output":"","status":"in_progress"}}',
    '{"type":"item.completed","item":{"id":"i1","type":"command_execution","command":"ls tools","aggregated_output":"a","exit_code":0,"status":"completed"}}',
    '{"type":"item.completed","item":{"id":"i2","type":"agent_message","text":"중간 말"}}',
    '{"type":"item.completed","item":{"id":"i3","type":"agent_message","text":"DONE 보고"}}',
    '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":50,"output_tokens":7}}',
]


def sdir(root, events=(), stderr=None):
    d = pathlib.Path(root)
    (d / "events.jsonl").write_text("".join(f"2026-11-12T10:00:00\t{ln}\n" for ln in events), encoding="utf-8")
    if stderr is not None:
        (d / "stderr.log").write_text(stderr, encoding="utf-8")
    return d


class CommandTest(unittest.TestCase):
    def spec(self, **kw):
        return SessionSpec(id="x", role="worker", harness="codex", brief_path="/b/brief.md", cwd=str(ROOT), **kw)

    def test_no_model(self):
        c = A.command(self.spec())
        self.assertEqual(c.argv, ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-C", str(ROOT),
                                  "--sandbox", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
                                  "--json", "-"])
        self.assertEqual(c.stdin_path, "/b/brief.md")
        self.assertEqual(c.cwd, str(ROOT))

    def test_model_provider(self):
        a = A.command(self.spec(model="kisti/kistillm")).argv
        self.assertEqual(a[-9:], ["-m", "kistillm", "-c", "model_provider=kisti",
                                  "-c", "model_providers.kisti.stream_max_retries=1",
                                  "-c", "model_providers.kisti.request_max_retries=1", "-"][-9:])
        self.assertEqual(a[-1], "-")

    def test_model_without_provider(self):
        a = A.command(self.spec(model="gpt-x")).argv
        self.assertEqual(a[-3:], ["-m", "gpt-x", "-"])
        self.assertFalse(any("model_provider" in x for x in a))

    def test_first_slash_split(self):
        # 공급자는 첫 '/' 앞이다 - 오픈라우터의 모델 id 는 '/' 를 품는다
        a = A.command(self.spec(model="openrouter/deepseek/deepseek-v4.1-flash")).argv
        self.assertEqual(a[a.index("-m") + 1], "deepseek/deepseek-v4.1-flash")
        self.assertIn("model_provider=openrouter", a)

    def test_real_success_sample_parses(self):
        # 실물 표본 (codex-cli 0.162.1, 오픈라우터 딥시크, 2026-11-12)
        import pathlib
        lines = (pathlib.Path(__file__).parent / "fixtures" / "harness" / "codex_ok_openrouter.jsonl").read_text().splitlines()
        kinds = [(e.kind if e else None) for e in map(A.parse_event, lines)]
        self.assertEqual(kinds, ["raw", "error", "raw", "tool", "tool", "text", "usage"])
        self.assertEqual(A.parse_event(lines[5]).text, "DONE")

    def test_cwd_refusal(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                A.command(SessionSpec(id="x", role="worker", harness="codex", brief_path="b", cwd=t))
            (pathlib.Path(t) / "tools").mkdir()
            (pathlib.Path(t) / "tools" / "fleet.py").write_text("")
            self.assertEqual(A.command(SessionSpec(id="x", role="worker", harness="codex", brief_path="b", cwd=t)).cwd, t)
        with self.assertRaises(ValueError):
            A.command(SessionSpec(id="x", role="worker", harness="codex", brief_path="b", cwd="/no/such/dir"))


class ParseTest(unittest.TestCase):
    def kinds(self, lines):
        return [(e.kind if e else None) for e in map(A.parse_event, lines)]

    def test_fixture_missing_key(self):
        lines = (FIX / "codex_error_missing_key.jsonl").read_text().splitlines()
        self.assertEqual(self.kinds(lines), ["raw", "raw", "error", "error"])
        self.assertIn("KISTI_API_KEY", A.parse_event(lines[3]).text)
        self.assertEqual(A.parse_event(lines[0]).data["harness_session_id"], "01a1cf9e-51b5-7093-92f9-703dda54bb5d")

    def test_fixture_stalled(self):
        lines = (FIX / "codex_stalled_no_response.jsonl").read_text().splitlines()
        self.assertEqual(self.kinds(lines), ["raw", "raw"])

    def test_hand_success(self):
        self.assertEqual(self.kinds(HAND), ["raw", "raw", None, "tool", "tool", "text", "text", "usage"])
        t = A.parse_event(HAND[4])
        self.assertEqual(t.text, "shell: ls tools")
        self.assertEqual(t.data, {"name": "shell", "input": {"command": "ls tools"}, "exit_code": 0})
        u = A.parse_event(HAND[7])
        self.assertEqual((u.data["tokens_in"], u.data["tokens_out"]), (100, 7))

    def test_long_command_one_line(self):
        ev = A.parse_event(json.dumps({"type": "item.started", "item": {"type": "command_execution", "command": "echo\n" + "x" * 300}}))
        self.assertNotIn("\n", ev.text)
        self.assertLessEqual(len(ev.text), 130)

    def test_other_tools(self):
        for item in ({"type": "file_change", "changes": [{"path": "a.py", "kind": "update"}]},
                     {"type": "mcp_tool_call", "server": "s", "tool": "t"},
                     {"type": "web_search", "query": "q"}):
            ev = A.parse_event(json.dumps({"type": "item.completed", "item": item}))
            self.assertEqual(ev.kind, "tool", item)

    def test_error_flags(self):
        r = A.parse_event('{"type":"error","message":"Reconnecting... 1/5"}')
        self.assertTrue(r.data.get("retry"))
        l = A.parse_event('{"type":"error","message":"429 Too Many Requests: rate limit"}')
        self.assertTrue(l.data.get("limit"))
        self.assertFalse(A.parse_event('{"type":"error","message":"boom"}').data)

    def test_raw_and_blank(self):
        self.assertIsNone(A.parse_event(""))
        self.assertIsNone(A.parse_event("   "))
        e = A.parse_event("not json {")
        self.assertEqual(e.kind, "raw")
        self.assertEqual(A.parse_event('{"type":"zzz"}').kind, "raw")
        self.assertEqual(A.parse_event('[1,2]').kind, "raw")
        self.assertEqual(A.parse_event('{"type":"item.completed","item":5}').kind, "raw")


class ReportTest(unittest.TestCase):
    def test_final_report_last_message(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(A.final_report(sdir(t, HAND)), "DONE 보고")

    def test_fallback_has_error(self):
        lines = (FIX / "codex_error_missing_key.jsonl").read_text().splitlines()
        with tempfile.TemporaryDirectory() as t:
            r = A.final_report(sdir(t, lines, stderr="\x1b[31mwarn x\x1b[0m\n$ ls\nreal line\n"))
            self.assertTrue(r.startswith("(최종 보고문 없음"))
            self.assertIn("KISTI_API_KEY", r)
            self.assertIn("real line", r)
            self.assertNotIn("$ ls", r)

    def test_empty(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(A.final_report(sdir(t, [])), "")

    def test_limit_signal(self):
        with tempfile.TemporaryDirectory() as t:
            d = pathlib.Path(t)
            sdir(t, ['{"type":"turn.failed","error":{"message":"You hit your usage limit"}}'])
            self.assertIs(A.limit_signal(d), True)
            sdir(t, HAND)
            self.assertIs(A.limit_signal(d), False)
            sdir(t, (FIX / "codex_stalled_no_response.jsonl").read_text().splitlines())
            self.assertIsNone(A.limit_signal(d))


class MiscTest(unittest.TestCase):
    def test_resume_none(self):
        self.assertIsNone(A.resume_command(None, "t", "m"))

    def test_probe(self):
        with mock.patch.object(codex_h.shutil, "which", return_value=None):
            self.assertFalse(A.probe().ok)
        cp = mock.Mock(returncode=0, stdout="codex-cli 0.162.1\n", stderr="")
        with mock.patch.object(codex_h.shutil, "which", return_value="/x/codex"), \
                mock.patch.object(codex_h.subprocess, "run", return_value=cp) as run:
            p = A.probe()
        self.assertTrue(p.ok)
        self.assertEqual(p.version, "0.162.1")
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_adapter(self):
        self.assertEqual(codex_h.ADAPTER.name, "codex")


if __name__ == "__main__":
    unittest.main()
