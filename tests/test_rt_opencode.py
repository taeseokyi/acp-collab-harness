import _fleet_env  # noqa: F401
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from fleet_rt import base
from fleet_rt.harness import opencode as opencode_h

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "harness" / "opencode_ok.jsonl"
SENT = "다음 파일이 이 지시의 전문이다. 읽고 그 안의 지시를 그대로 수행하라(파일 자체는 수정하지 말라): "
A = opencode_h.ADAPTER


def _repo(tmp):
    root = pathlib.Path(tmp)
    (root / "tools").mkdir()
    (root / "tools" / "fleet.py").write_text("")
    return root


def _spec(cwd, **kw):
    d = dict(id="T-1", role="worker", harness="opencode", brief_path=str(pathlib.Path(cwd) / "x" / "brief.md"),
             cwd=str(cwd))
    d.update(kw)
    return base.SessionSpec(**d)


def _session(tmp, lines, stderr=None):
    d = pathlib.Path(tmp) / "sess"
    d.mkdir()
    (d / "events.jsonl").write_text(
        "".join(f"2026-11-12T10:00:00\t{l}\n" for l in lines), encoding="utf-8")
    if stderr is not None:
        (d / "stderr.log").write_text(stderr, encoding="utf-8")
    return d


def _fixture_lines():
    return [l for l in FIX.read_text(encoding="utf-8").splitlines() if l.strip()]


def _ev(type_, **kw):
    return json.dumps({"type": type_, "sessionID": "ses_x", **kw})


class CommandTest(unittest.TestCase):
    def test_argv_with_ident_and_model(self):
        with tempfile.TemporaryDirectory() as t:
            root = _repo(t)
            c = A.command(_spec(root, model="kisti/kistillm", ident="  [S2 d27e93 REV 1] "))
            self.assertEqual(c.argv, ["opencode", "run", "--format", "json", "-m", "kisti/kistillm",
                                      "[S2 d27e93 REV 1] " + SENT + "x/brief.md"])
            self.assertEqual(c.cwd, str(root))
            self.assertIsNone(c.stdin_path)

    def test_argv_without_model_or_ident(self):
        with tempfile.TemporaryDirectory() as t:
            root = _repo(t)
            c = A.command(_spec(root))
            self.assertEqual(c.argv, ["opencode", "run", "--format", "json", SENT + "x/brief.md"])

    def test_brief_outside_cwd_is_absolute(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as o:
            root = _repo(t)
            brief = str(pathlib.Path(o) / "brief.md")
            c = A.command(_spec(root, brief_path=brief))
            self.assertEqual(c.argv[-1], SENT + brief)

    def test_brief_body_never_on_argv(self):
        with tempfile.TemporaryDirectory() as t:
            root = _repo(t)
            (root / "x").mkdir()
            body = "SECRET-BODY-aimem_monitor"
            (root / "x" / "brief.md").write_text(body)
            c = A.command(_spec(root))
            self.assertFalse(any(body in a for a in c.argv))

    def test_cwd_refusal(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                A.command(_spec(t))                       # tools/fleet.py 없음
            with self.assertRaises(ValueError):
                A.command(_spec(pathlib.Path(t) / "nope"))  # 없는 폴더
            (pathlib.Path(t) / "tools").mkdir()
            with self.assertRaises(ValueError):
                A.command(_spec(t))                       # tools 만 있고 fleet.py 없음
            _repo_ok = _repo(tempfile.mkdtemp(dir=t))
            A.command(_spec(_repo_ok))

    def test_resume_command_is_not_supported(self):
        self.assertIsNone(A.resume_command(None, "ses_1", "msg.md"))     # 작업자는 일회성


class ParseTest(unittest.TestCase):
    def test_fixture_kinds(self):
        evs = [A.parse_event(l) for l in _fixture_lines()]
        kinds = [e.kind if e else None for e in evs]
        # step_start, text(공백뿐), tool_use, step_finish, step_start, text, step_finish
        self.assertEqual(kinds, ["raw", None, "tool", "usage", "raw", "text", "usage"])
        self.assertEqual(evs[0].data["harness_session_id"], "ses_e305744ffffeSL7OTKV7J5EAgL")
        tool = evs[2]
        self.assertEqual(tool.text, "bash: echo fleet-sample")
        self.assertEqual(tool.data["name"], "bash")
        self.assertEqual(tool.data["status"], "completed")
        self.assertEqual(tool.data["input"], {"command": "echo fleet-sample"})
        self.assertEqual(evs[5].text.strip(), "DONE")
        self.assertEqual(evs[3].data["reason"], "tool-calls")
        self.assertEqual(evs[3].data["tokens_in"], 11165)
        self.assertEqual(evs[3].data["tokens_out"], 52)
        self.assertEqual(evs[3].data["cost_usd"], 0)
        self.assertEqual(evs[6].data["reason"], "stop")
        self.assertEqual(evs[6].data["tokens_out"], 25)

    def test_tool_without_title_uses_input(self):
        e = A.parse_event(_ev("tool_use", part={"tool": "read", "state": {
            "status": "running", "input": {"filePath": "tools/fleet.py"}}}))
        self.assertEqual(e.text, "read: tools/fleet.py")

    def test_tool_summary_truncated(self):
        e = A.parse_event(_ev("tool_use", part={"tool": "bash", "state": {"title": "x" * 500}}))
        self.assertLessEqual(len(e.text), 130)

    def test_blank_and_non_json(self):
        self.assertIsNone(A.parse_event(""))
        self.assertIsNone(A.parse_event("   \n"))
        e = A.parse_event("not json at all")
        self.assertEqual(e.kind, "raw")
        self.assertEqual(e.text, "not json at all")
        self.assertEqual(A.parse_event("[1,2]").kind, "raw")
        self.assertEqual(A.parse_event(_ev("something_new")).kind, "raw")

    def test_error_events(self):
        e = A.parse_event(_ev("error", error={"name": "APIError", "data": {
            "message": "Provider response headers timed out after 300000ms"}}))
        self.assertEqual(e.kind, "error")
        self.assertIn("timed out", e.text)
        self.assertTrue(e.data.get("timeout"))
        self.assertFalse(e.data.get("limit"))
        e = A.parse_event(_ev("error", error={"name": "APIError", "data": {"message": "429 Too Many Requests"}}))
        self.assertTrue(e.data.get("limit"))
        e = A.parse_event(_ev("error", error={"name": "Boom"}))
        self.assertEqual(e.kind, "error")
        self.assertEqual(e.data, {})
        self.assertEqual(A.parse_event(_ev("error")).kind, "error")


class ReportTest(unittest.TestCase):
    def test_fixture_report_and_limit(self):
        with tempfile.TemporaryDirectory() as t:
            d = _session(t, _fixture_lines())
            self.assertEqual(A.final_report(d), "DONE")
            self.assertIs(A.limit_signal(d), False)

    def test_last_step_without_text_falls_back(self):
        with tempfile.TemporaryDirectory() as t:
            lines = _fixture_lines()[:-3] + [_ev("step_start"), _ev("step_finish", part={"reason": "stop"})]
            lines = [l for l in lines]
            # 앞 step 의 text 는 공백뿐 -> 비지 않은 text 가 없으니 보고문 없음 경로
            d = _session(t, lines, stderr="boom happened\n")
            self.assertTrue(A.final_report(d).startswith("(최종 보고문 없음"))
            lines2 = [_ev("step_start"), _ev("text", part={"text": "앞 보고"}), _ev("step_start"),
                      _ev("step_finish", part={"reason": "stop"})]
            d2 = pathlib.Path(t) / "s2"
            d2.mkdir()
            (d2 / "events.jsonl").write_text("\n".join("t\t" + l for l in lines2))
            self.assertEqual(A.final_report(d2), "앞 보고")

    def test_multiple_text_parts_of_last_step_joined(self):
        with tempfile.TemporaryDirectory() as t:
            d = _session(t, [_ev("step_start"), _ev("text", part={"text": "옛"}), _ev("step_start"),
                             _ev("text", part={"text": "\n가"}), _ev("text", part={"text": "나\n"})])
            self.assertEqual(A.final_report(d), "가나")

    def test_no_report_includes_stderr_and_errors(self):
        with tempfile.TemporaryDirectory() as t:
            d = _session(t, [_ev("error", error={"name": "E", "data": {
                "message": "Provider response headers timed out after 300000ms"}})],
                stderr="\x1b[31mfatal line\x1b[0m\n> build · x\n")
            r = A.final_report(d)
            self.assertTrue(r.startswith("(최종 보고문 없음 - 작업자가 보고 전에 끝남. stderr 꼬리:)\n"))
            self.assertIn("fatal line", r)
            self.assertIn("headers timed out", r)
            self.assertNotIn("\x1b", r)
            self.assertNotIn("build ·", r)

    def test_empty_everything(self):
        with tempfile.TemporaryDirectory() as t:
            d = _session(t, [])
            self.assertEqual(A.final_report(d), "")
            self.assertEqual(A.final_report(pathlib.Path(t) / "missing"), "")


class LimitTest(unittest.TestCase):
    def test_true_on_limit_error(self):
        with tempfile.TemporaryDirectory() as t:
            d = _session(t, [_ev("step_start"), _ev("error", error={"name": "E", "data": {
                "message": "rate limit exceeded"}})])
            self.assertIs(A.limit_signal(d), True)

    def test_timeout_error_is_not_limit(self):
        with tempfile.TemporaryDirectory() as t:
            d = _session(t, [_ev("error", error={"name": "E", "data": {
                "message": "Provider response headers timed out after 300000ms"}})])
            self.assertIsNone(A.limit_signal(d))

    def test_none_when_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            d = _session(t, _fixture_lines()[:4])      # tool-calls 로 끝남
            self.assertIsNone(A.limit_signal(d))
            self.assertIsNone(A.limit_signal(pathlib.Path(t) / "missing"))


class ProbeTest(unittest.TestCase):
    def test_missing(self):
        with mock.patch.object(opencode_h.shutil, "which", return_value=None):
            r = A.probe()
        self.assertFalse(r.ok)

    def test_ok_mocked(self):
        cp = subprocess.CompletedProcess(["opencode"], 0, stdout="1.18.33\n", stderr="")
        with mock.patch.object(opencode_h.shutil, "which", return_value="/x/opencode"), \
                mock.patch.object(opencode_h.subprocess, "run", return_value=cp) as run:
            r = A.probe()
        self.assertTrue(r.ok)
        self.assertEqual((r.binary, r.version), ("/x/opencode", "1.18.33"))
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_registry(self):
        self.assertIs(opencode_h.ADAPTER.name, "opencode")


if __name__ == "__main__":
    unittest.main()
