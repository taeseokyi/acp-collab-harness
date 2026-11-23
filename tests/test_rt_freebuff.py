import _fleet_env  # noqa: F401
"""freebuff 하네스 - 사람이 '보내기' 를 눌러야 팬에 지시가 나간다.

진짜 tmux·freebuff 는 쓰지 않는다: PATH 앞에 가짜 `tmux` (받은 인자를 적고, `capture-pane` 에는 파일의 화면을 준다)를
두고, 대화 파일은 검사가 써 준다.
"""
import contextlib
import io
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import fleet
import fleet_graph
from fleet_rt import harness
from fleet_rt.harness import freebuff as fb

READY = "\n".join([
    " 8m left · 16.2K (12%)                      ✕ End session",
    "╭──────────────────────────────╮",
    "│  ▍Enter a coding task or / for commands  │",
    "╰──────────────────────────────╯",
    " DeepSeek V4.1 Flash Slow · ~/work/ai-fleet · /model to change · Chat: chat",
    " ← for history · ? for help"])
BUSY = READY.replace("Enter a coding task or / for commands", "무언가 치는 중")

FAKE_TMUX = """#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_TMUX_DIR"]
with open(os.path.join(d, "log.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\\n")
after = os.path.join(d, "screen_after_line.txt")
if sys.argv[1] == "send-keys" and "-l" in sys.argv and sys.argv[-1] != "/new" and os.path.exists(after):
    os.replace(after, os.path.join(d, "screen.txt"))
if sys.argv[1] == "capture-pane":
    sys.stdout.write(open(os.path.join(d, "screen.txt"), encoding="utf-8").read())
"""


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.root = self.tmp / "repo"
        (self.root / "tools").mkdir(parents=True)
        (self.root / "tools" / "fleet.py").write_text("", encoding="utf-8")
        self.chats = self.tmp / "chats"
        (self.root / "fleet.toml").write_text(
            '[providers.freebuff]\ntier = "free"\n[harness.freebuff]\nproviders = ["freebuff"]\n'
            f'pane = "fb:0.0"\nchats = "{self.chats}"\n', encoding="utf-8")
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "tmux").write_text(FAKE_TMUX, encoding="utf-8")
        (self.bin / "tmux").chmod(0o755)
        self.screen(READY)
        env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "FAKE_TMUX_DIR": str(self.tmp)}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.procs = []
        self.addCleanup(self._kill)

    def _kill(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)
            p.stdout.close()

    def screen(self, text):
        (self.tmp / "screen.txt").write_text(text, encoding="utf-8")

    def sent_keys(self):
        try:
            rows = [json.loads(x) for x in (self.tmp / "log.jsonl").read_text(encoding="utf-8").splitlines()]
        except OSError:
            return []
        return [r[3:] for r in rows if r and r[0] == "send-keys"]

    def session(self, sid="T-900-S6-a1-000000"):
        d = self.root / ".aimem" / "sessions" / sid
        d.mkdir(parents=True)
        (d / "brief.md").write_text("SLOT=S6 T-900\n확인토큰: abc123\n\n비밀 본문 rm -rf\n", encoding="utf-8")
        (d / "meta.json").write_text(json.dumps({
            "id": sid, "cwd": str(self.root), "harness": "freebuff", "brief_path": str(d / "brief.md"),
            "ident": "[AIMEM 작업자 지시] 슬롯 S6 · 확인토큰 abc123 · AIMEM REV 1."}), encoding="utf-8")
        return d

    def line(self, d, text="이 파일 읽고 해 줘:"):
        return fb.compose_line(text, fb.brief_ref(d, self.root))[0]

    def drive(self, d):
        p = subprocess.Popen([sys.executable, fb.__file__, str(d)], stdout=subprocess.PIPE, text=True,
                             cwd=str(self.root))
        self.procs.append(p)
        return p

    def wait_for(self, cond, sec=10):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            v = cond()
            if v:
                return v
            time.sleep(0.05)
        self.fail("기다리던 일이 일어나지 않음")

    def sent_line(self, d, nth=1):
        """팬에 들어간 지시 줄 (nth 번째)."""
        return self.wait_for(lambda: (lambda ls: ls[nth - 1] if len(ls) >= nth else None)(
            [k[2] for k in self.sent_keys() if len(k) == 3 and d.name in k[2]]))

    def chat(self, msgs):
        """freebuff 가 대화를 디스크에 적은 것처럼."""
        c = self.chats / self.root.name / "chats" / "2026-11-20T00-00-00.000Z"
        c.mkdir(parents=True, exist_ok=True)
        (c / "chat-messages.json").write_text(json.dumps(msgs), encoding="utf-8")

    def answer(self, d, blocks, complete=True, **more):
        """지시 한 줄과 그 답 하나. 정상으로 끝난 답에는 freebuff 가 `completionTime` 을 적는다."""
        line = self.sent_line(d)
        ai = dict({"variant": "ai", "content": "", "blocks": blocks, "isComplete": complete},
                  **({"completionTime": "1s"} if complete and not more else {}), **more)
        self.chat([{"variant": "user", "content": line}, ai])
        return line

    def inproc(self, d, script, quiet=1.0, cpu=None):
        """운전기를 이 프로세스에서 돌린다(멈춤 한도를 줄이려고). `script(d)` 는 옆 스레드에서 돈다. `(rc, 출력)`."""
        old = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        out = io.StringIO()
        t = threading.Thread(target=script, args=(d,), daemon=True)
        try:
            with mock.patch.object(fb, "QUIET_SEC", quiet), mock.patch.object(fb, "CPU_CHECK_SEC", 0.2), \
                    mock.patch.object(fb, "POLL_SEC", 0.1), mock.patch.object(fb, "SETTLE_SEC", 0.2), \
                    mock.patch.object(fb.Driver, "_pane_cpu", cpu or (lambda self: 0.0)), \
                    contextlib.redirect_stdout(out):
                drv = fb.Driver(d)
                t.start()
                rc = drv.run()
        finally:
            for sig, h in old.items():
                signal.signal(sig, h)
        t.join(5)
        return rc, out.getvalue()

    def approve_when_waiting(self, d):
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "await")
        fb.approve(d, "웹", self.line(d))


class Driver(Base):
    def test_nothing_is_typed_until_a_person_sends_and_then_the_chosen_line(self):
        d = self.session()
        p = self.drive(d)
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "await")
        time.sleep(1.2)
        self.assertEqual(self.sent_keys(), [], "보내기 전에 팬에 무엇인가 넣었다")
        self.assertEqual(fb.ADAPTER.final_report(d), "", "기다리는 중인데 보고가 있다")
        self.assertEqual(fb.approve(d, "웹(검사)", self.line(d)), (True, ""))
        line = self.answer(d, [
            {"type": "text", "textType": "reasoning", "content": "생각"},
            {"type": "tool", "toolName": "read_files", "input": {"paths": ["a.py"]}},
            {"type": "text", "textType": "text", "content": "DONE\n고친 것 없음"}])
        out, _ = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, out)
        keys = self.sent_keys()
        self.assertEqual(keys, [["-l", "--", "/new"], ["Enter"], ["-l", "--", line], ["Enter"]])
        self.assertEqual(line, self.line(d))
        self.assertTrue(line.endswith(f".aimem/sessions/{d.name}/brief.md"))
        self.assertNotIn("비밀 본문", json.dumps(keys, ensure_ascii=False), "지시 본문이 팬에 들어갔다")
        self.assertFalse((d / fb.APPROVE_FILE).exists())
        gate = fb.read_gate(d)
        self.assertEqual((gate["phase"], gate["by"]), ("done", "웹(검사)"))
        self.assertTrue(gate["sent_at"])
        (d / "events.jsonl").write_text("".join(f"t\t{ln}\n" for ln in out.splitlines()), encoding="utf-8")
        self.assertEqual(fb.ADAPTER.final_report(d), "DONE\n고친 것 없음")
        kinds = [fb.ADAPTER.parse_event(ln).kind for ln in out.splitlines()]
        self.assertIn("text", kinds)
        self.assertNotIn("생각", out)

    def test_busy_pane_refuses_and_waits_for_another_press(self):
        d = self.session()
        self.screen(BUSY)
        self.drive(d)
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "await")
        fb.approve(d, "웹", self.line(d))
        g = self.wait_for(lambda: (fb.read_gate(d) or {}).get("error") and fb.read_gate(d))
        self.assertEqual(g["phase"], "await")
        self.assertIn("입력 칸", g["error"])
        self.assertEqual(self.sent_keys(), [])
        self.assertFalse((d / fb.APPROVE_FILE).exists(), "못 보낸 승인이 남아 저절로 다시 나간다")
        self.screen(READY)
        time.sleep(1.0)
        self.assertEqual(self.sent_keys(), [], "사람이 다시 누르지 않았는데 보냈다")
        self.assertEqual(fb.approve(d, "웹", self.line(d)), (True, ""))
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "sent")

    def test_cut_while_waiting_types_nothing(self):
        d = self.session()
        p = self.drive(d)
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "await")
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=10)
        self.assertEqual(p.returncode, fb.RC_UNSENT)
        self.assertEqual(self.sent_keys(), [])
        self.assertEqual(fb.read_gate(d)["phase"], "unsent")
        (d / "events.jsonl").write_text("".join(f"t\t{ln}\n" for ln in out.splitlines()), encoding="utf-8")
        self.assertTrue(fb.ADAPTER.final_report(d).startswith("BLOCKED"))

    def test_quiet_after_send_is_cut_and_keeps_what_was_written(self):
        # 시간 한도는 없다 - 답이 자라지도, freebuff 가 CPU 를 쓰지도 않을 때만 멈춘 것으로 보고 끊는다. 쓰던 글은 보고로 넘긴다.
        def script(d):
            self.approve_when_waiting(d)
            self.answer(d, [{"type": "text", "textType": "text", "content": "쓰는 중"}], complete=False)
        d = self.session()
        rc, out = self.inproc(d, script)
        self.assertEqual(rc, fb.RC_TIMEOUT, out)
        self.assertEqual(self.sent_keys()[-1], ["Escape"])
        self.assertEqual(fb.read_gate(d)["phase"], "timeout")
        self.assertIn("쓰는 중", json.loads(out.splitlines()[-1])["result"])

    def test_cpu_use_or_a_growing_answer_waits_without_a_cap(self):
        # 멈춤 한도(1초)를 몇 배 넘겨도, freebuff 가 CPU 를 쓰고 있으면 끊지 않는다
        t0 = time.monotonic()

        def script(d):
            self.approve_when_waiting(d)
            time.sleep(4)
            self.answer(d, [{"type": "text", "textType": "text", "content": "DONE\n오래 걸림"}])
        d = self.session()
        rc, out = self.inproc(d, script, cpu=lambda self: time.monotonic())      # 늘 코어 하나를 다 쓰는 중
        self.assertEqual(rc, 0, out)
        self.assertGreater(time.monotonic() - t0, 4)
        self.assertEqual(json.loads(out.splitlines()[-1])["result"], "DONE\n오래 걸림")

    def test_interrupted_answer_is_not_a_success(self):
        # freebuff 는 끊긴 답에도 isComplete 를 붙인다 - 정상으로 끝난 답에만 completionTime 이 있다 (R37 실물)
        def script(d):
            self.approve_when_waiting(d)
            self.answer(d, [{"type": "text", "textType": "text", "content": "보고 쓰던 중\n\n[response interrupted]"}],
                        completionTime=None)
        d = self.session()
        rc, out = self.inproc(d, script, quiet=30)
        self.assertEqual(rc, 1, out)
        self.assertEqual(fb.read_gate(d)["phase"], "failed")
        end = json.loads(out.splitlines()[-1])
        self.assertEqual(end["ok"], False)
        self.assertIn("보고 쓰던 중", end["result"])

    def test_ended_session_continues_in_the_same_chat(self):
        # 세션이 끝나 멈춘 답은 성공이 아니다. 한 일이 있으면 다시 보내기를 기다렸다가 **같은 대화에** 이어 보낸다 (새 대화를 열지 않는다)
        ended = {"variant": "ai", "content": "", "isComplete": True, "userError": "Your free session ended, so the agent stopped here.",
                 "blocks": [{"type": "tool", "toolName": "read_files", "input": {"paths": ["a.py"]}}]}
        d = self.session()
        p = self.drive(d)
        self.approve_when_waiting(d)
        line = self.sent_line(d)
        self.chat([{"variant": "user", "content": line}, ended])
        g = self.wait_for(lambda: (lambda g: g if g.get("resume") and g.get("phase") == "await" else None)(fb.read_gate(d) or {}))
        self.assertIsNone(g.get("error"))
        self.assertIsNone(p.poll(), "세션이 끝난 답을 끝으로 봤다")
        again = self.line(d, "하던 데서 이어서 해 줘:")
        self.assertEqual(fb.approve(d, "웹", again), (True, ""))
        self.assertEqual(self.sent_line(d, 2), again)
        time.sleep(1.0)
        self.assertIsNone(p.poll(), "이어 보낸 뒤 옛 답을 새 답으로 봤다")
        self.chat([{"variant": "user", "content": line}, ended, {"variant": "user", "content": again},
                   {"variant": "ai", "content": "", "isComplete": True, "completionTime": "3s",
                    "blocks": [{"type": "text", "textType": "text", "content": "DONE\n이어서 끝냄"}]}])
        out, _ = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, out)
        self.assertEqual([k for k in self.sent_keys() if k == ["-l", "--", "/new"]], [["-l", "--", "/new"]])
        self.assertEqual(json.loads(out.splitlines()[-1])["result"], "DONE\n이어서 끝냄")
        self.assertEqual(out.count('"read_files"'), 1, "앞 답의 조각을 두 번 내보냈다")

    def test_ending_again_without_progress_gives_up(self):
        ended = {"variant": "ai", "content": "", "isComplete": True, "userError": "Your free session ended.", "blocks": []}

        def script(d):
            self.approve_when_waiting(d)
            line = self.sent_line(d)
            self.chat([{"variant": "user", "content": line}, ended])
            self.wait_for(lambda: (fb.read_gate(d) or {}).get("resume"))
            self.approve_when_waiting(d)
            again = self.sent_line(d, 2)
            self.chat([{"variant": "user", "content": line}, ended, {"variant": "user", "content": again}, ended])
        d = self.session()
        rc, out = self.inproc(d, script, quiet=30)
        self.assertEqual(rc, 1, out)
        self.assertIn("free session ended", out)

    def test_cut_while_working_hands_over_what_was_written(self):
        d = self.session()
        p = self.drive(d)
        self.approve_when_waiting(d)
        self.answer(d, [{"type": "tool", "toolName": "read_files", "input": {}},
                        {"type": "text", "textType": "text", "content": "지적 1 ...\n지적 2 (쓰는 중"}], complete=False)
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "sent")
        time.sleep(3)                    # 운전기가 대화 파일을 읽을 틈
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=10)
        self.assertEqual(p.returncode, 143, out)
        self.assertEqual(fb.read_gate(d)["phase"], "cut")
        self.assertIn("지적 1", json.loads(out.splitlines()[-1])["result"])


class Pieces(Base):
    def test_approve_only_while_waiting(self):
        d = self.session()
        self.assertFalse(fb.approve(d, "웹", self.line(d))[0])                      # 운전기가 아직 안 떴다
        (d / fb.GATE_FILE).write_text(json.dumps({"phase": "sent"}), encoding="utf-8")
        self.assertFalse(fb.approve(d, "웹", self.line(d))[0])
        (d / fb.GATE_FILE).write_text(json.dumps({"phase": "await", "busy": True}), encoding="utf-8")
        self.assertFalse(fb.approve(d, "웹", self.line(d))[0])                      # 팬에 넣는 중
        (d / fb.GATE_FILE).write_text(json.dumps({"phase": "await"}), encoding="utf-8")
        (d / "end.json").write_text("{}", encoding="utf-8")
        self.assertFalse(fb.approve(d, "웹", self.line(d))[0])
        self.assertFalse((d / fb.APPROVE_FILE).exists())

    def test_line_is_the_humans_phrase_plus_brief_path(self):
        ref = ".aimem/sessions/X/brief.md"
        self.assertEqual(fb.compose_line("  이거  읽고 해 줘: ", ref), ("이거 읽고 해 줘: " .strip() + " " + ref, ""))
        for bad in ("", "   ", None, "/bash rm -rf ~", "@x", "!ls", "a\nb", "가" * (fb.LINE_TEXT_MAX + 1)):
            self.assertIsNone(fb.compose_line(bad, ref)[0], bad)
        self.assertEqual(fb.send_line("fb:0.0", "/bash ls")[0], False)
        self.assertEqual(fb.send_line("fb:0.0", "a\nb")[0], False)
        self.assertEqual(self.sent_keys(), [])

    def test_expired_session_is_reported_not_silent(self):
        d = self.session()
        self.drive(d)
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "await")
        fb.approve(d, "웹", self.line(d))
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "sent")
        self.screen(READY.replace("│  ▍Enter a coding task or / for commands  │",
                                  "│ This session was released. Choose a model to start a new session. │"))
        self.assertTrue(fb.pane_status("fb:0.0")["held"])
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("held"))
        self.screen(BUSY)                                    # 사람이 팬에서 풀었다
        self.wait_for(lambda: not (fb.read_gate(d) or {}).get("held"))
        self.assertEqual((fb.read_gate(d) or {}).get("phase"), "sent")

    def test_released_session_gets_one_more_enter(self):
        (self.tmp / "screen_after_line.txt").write_text(READY.replace(
            "│  ▍Enter a coding task or / for commands  │",
            "│ This session was released. Choose a model to start a new session. │\n│ Enter: retry  Esc: back to draft │"),
            encoding="utf-8")
        self.assertEqual(fb.send_line("fb:0.0", "해 줘: a/brief.md"), (True, ""))
        self.assertEqual(self.sent_keys(), [["-l", "--", "/new"], ["Enter"], ["-l", "--", "해 줘: a/brief.md"], ["Enter"], ["Enter"]])

    def test_ready_session_gets_no_extra_enter(self):
        with mock.patch.object(fb, "HELD_CHECKS", 1):
            self.assertEqual(fb.send_line("fb:0.0", "해 줘: a/brief.md"), (True, ""))
        self.assertEqual([k for k in self.sent_keys() if k == ["Enter"]], [["Enter"], ["Enter"]])

    def test_no_phrase_no_send(self):
        d = self.session()
        (d / fb.GATE_FILE).write_text(json.dumps({"phase": "await"}), encoding="utf-8")
        self.assertFalse(fb.approve(d, "웹", "")[0])
        self.assertFalse((d / fb.APPROVE_FILE).exists())
        self.drive(d)
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("phase") == "await")
        (d / fb.APPROVE_FILE).write_text(json.dumps({"by": "누군가"}), encoding="utf-8")   # 문구 없는 승인 파일
        self.wait_for(lambda: (fb.read_gate(d) or {}).get("error"))
        self.assertEqual(self.sent_keys(), [])

    def test_pane_status(self):
        st = fb.pane_status("fb:0.0")
        self.assertEqual((st["ok"], st["left"], st["model"]), (True, "8m", "DeepSeek V4.1 Flash Slow"))
        self.screen(READY.replace(" 8m left · 16.2K (12%)", " 16.2K (12%)"))
        st = fb.pane_status("fb:0.0")
        self.assertEqual((st["ok"], st["left"]), (True, None))
        self.screen("$ ")
        self.assertFalse(fb.pane_status("fb:0.0")["ok"])

    def test_chat_blocks_only_after_our_instruction(self):
        msgs = [{"variant": "user", "content": "다른 말"},
                {"variant": "ai", "blocks": [{"type": "text", "textType": "text", "content": "남의 답"}], "isComplete": True},
                {"variant": "user", "content": "… T-900-S6 …"},
                {"variant": "ai", "isComplete": True, "blocks": [
                    {"type": "text", "textType": "text", "content": "먼저 본다"},
                    {"type": "tool", "toolName": "run", "input": "ls"},
                    {"type": "text", "textType": "text", "content": "DONE"},
                    {"type": "text", "textType": "text", "content": "끝"}]}]
        blocks, done = fb.chat_blocks(msgs, "T-900-S6")
        self.assertTrue(done)
        self.assertEqual(blocks[0], ("text", "먼저 본다"))
        self.assertEqual(fb.final_text(blocks), "DONE\n\n끝")

    def test_registered_and_marked(self):
        self.assertIn("freebuff", harness.REAL)
        self.assertTrue(harness.needs_approval("freebuff"))
        for h in ("claude", "codex", "opencode", "fake", "없는것"):
            self.assertFalse(harness.needs_approval(h))


class GraphRules(unittest.TestCase):
    """그래프: 승인 슬롯 노드에는 의존을 못 걸고, 기다리는 시간은 한도로 안 세고, 안 보낸 채 남으면 넘긴다."""

    def setUp(self):
        for attr, value in (("roster", {"S1": ("a", "claude"), "S6": ("f", "freebuff")}), ("owned_paths", []),
                            ("_slot_model", None), ("paused_slots", {})):
            p = mock.patch.object(fleet, attr, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(fleet_graph, "_log")
        p.start()
        self.addCleanup(p.stop)

    def _g(self):
        return {"id": "G-1", "nodes": [
            {"id": "T-1", "slot": "S1", "task": "x", "deps": [], "status": "done", "attempts": []},
            {"id": "T-2", "slot": "S6", "task": "x", "deps": [], "status": "running",
             "attempts": [{"run_id": "R2", "started": "2020-01-01T00:00:00"}]}]}

    def test_no_node_may_depend_on_an_approval_slot(self):
        g = {"id": "G-1", "nodes": [{"id": "T-1", "slot": "S6", "task": "x", "deps": []},
                                    {"id": "T-2", "slot": "S1", "task": "x", "deps": ["T-1"]}]}
        self.assertTrue(any("보내기" in p for p in fleet_graph.validate_graph(g)))
        g["nodes"][1]["deps"] = []
        self.assertEqual(fleet_graph.validate_graph(g), [])

    def test_unsent_node_is_handed_over_when_everything_else_ended(self):
        g = self._g()
        old = {"phase": "await", "since": "2020-01-01T00:00:00"}
        with mock.patch.object(fleet, "run_gate", return_value=old), \
                mock.patch.object(fleet_graph, "_kill_run", return_value=(1, "killed")) as kill:
            self.assertTrue(fleet_graph._cut_unsent(g))
            kill.assert_called_once()
        n = g["nodes"][1]
        self.assertEqual((n["status"], n["attempts"][-1]["state"]), ("blocked", "unsent"))

    def test_kept_while_other_work_remains_or_just_started_or_already_sent(self):
        cases = []
        g = self._g()
        g["nodes"][0]["status"] = "running"
        cases.append((g, {"phase": "await", "since": "2020-01-01T00:00:00"}))
        cases.append((self._g(), {"phase": "await", "since": fleet_graph._now()}))
        cases.append((self._g(), {"phase": "sent", "since": "2020-01-01T00:00:00", "sent_at": "2020-01-01T00:00:01"}))
        for g, gate in cases:
            with mock.patch.object(fleet, "run_gate", side_effect=lambda rid, gate=gate: gate if rid == "R2" else None), \
                    mock.patch.object(fleet_graph, "_kill_run") as kill:
                self.assertFalse(fleet_graph._cut_unsent(g), gate)
                kill.assert_not_called()
            self.assertEqual(g["nodes"][1]["status"], "running")


class SlotRules(unittest.TestCase):
    """freebuff 슬롯은 사람만 둔다 - 관리자 세션은 더하지 못한다."""

    def test_manager_cannot_add_an_approval_slot(self):
        import aimem_db
        with mock.patch.object(aimem_db, "manager_caller", return_value={"round": 1, "policy": "cost"}):
            with self.assertRaises(ValueError) as cm:
                aimem_db.slot_add(None, "freebuff")
            self.assertIn("사람만", str(cm.exception))
            aimem_db._no_approval_slot_by_manager({"round": 1, "policy": "cost"}, "claude")     # 다른 하네스는 막지 않는다
        aimem_db._no_approval_slot_by_manager(None, "freebuff")                                # 사람은 막지 않는다


class MonitorSend(Base):
    """모니터의 보기·고치기·보내기. 승인 파일을 쓰는 곳은 여기 하나다."""

    def setUp(self):
        super().setUp()
        from aimem_monitor import server
        self.server = server
        self.d = self.session()
        (self.d / fb.GATE_FILE).write_text(json.dumps({"phase": "await", "since": "2026-11-20T10:00:00"}), encoding="utf-8")

    def test_info_gives_no_phrase(self):
        code, info = self.server.pane_info(self.d.name, self.root)
        self.assertEqual(code, 200, info)
        self.assertEqual(info["phase"], "await")
        self.assertEqual(info["ref"], f".aimem/sessions/{self.d.name}/brief.md")
        self.assertNotIn("line", info)
        self.assertNotIn("body", info)
        self.assertTrue(info["pane"]["ok"])

    def test_send_carries_the_humans_phrase_and_leaves_brief(self):
        before = (self.d / "brief.md").read_text(encoding="utf-8")
        code, res = self.server.pane_send(self.d.name, {"action": "send", "text": "오늘은 이거 부탁해:"}, "웹(검사)", self.root)
        self.assertEqual(code, 200, res)
        ap = json.loads((self.d / fb.APPROVE_FILE).read_text(encoding="utf-8"))
        self.assertEqual((ap["by"], ap["line"]), ("웹(검사)", f"오늘은 이거 부탁해: .aimem/sessions/{self.d.name}/brief.md"))
        self.assertEqual((self.d / "brief.md").read_text(encoding="utf-8"), before)

    def test_kind_comes_from_engine_facts(self):
        k = self.server._pane_kind
        self.assertEqual(k({"write_paths": []}, {}), "read")
        self.assertEqual(k({"write_paths": ["tools/a.py"], "attempt": 2}, {}), "retry")
        self.assertEqual(k({"write_paths": []}, {"error": "못 보냄"}), "retry")
        self.assertEqual(k({"write_paths": [], "attempt": 2}, {"resume": True}), "resume")   # 세션이 끝난 뒤 이어 보내기
        self.assertEqual(k({"write_paths": ["tools/a.py"], "label": "T-1 적대적 검수"}, {}), "review")
        self.assertEqual(k({"write_paths": ["docs/A.md"]}, {}), "docs")
        self.assertEqual(k({"write_paths": ["tests/test_a.py"]}, {}), "test")
        self.assertEqual(k({"write_paths": ["tools/a.py", "tests/test_a.py"]}, {}), "edit")
        self.assertEqual(self.server.pane_info(self.d.name, self.root)[1]["kind"], "read")

    def test_auto_send_after_wait_unless_held_or_off(self):
        s = self.server
        self.assertEqual(s.pane_auto_tick(self.root), [])                       # 꺼져 있다
        s.pane_auto_set(True, "웹(검사)", self.root)
        view = s.pane_auto_view(self.root)[1]
        self.assertTrue(view["on"] and 0 < view["runs"][self.d.name]["due_in"] <= s.PANE_AUTO_SEC)
        self.assertEqual(s.pane_auto_tick(self.root), [])                       # 아직 10초가 안 됐다
        with mock.patch.object(s, "PANE_AUTO_SEC", 0):
            self.screen(BUSY)
            self.assertEqual(s.pane_auto_tick(self.root), [])                   # 팬이 바쁘다
            self.screen(READY)
            self.assertEqual(s.pane_send(self.d.name, {"action": "hold"}, "웹", self.root)[0], 200)
            self.assertEqual(s.pane_auto_tick(self.root), [])                   # 사람이 붙잡았다
            (self.d / s.PANE_HOLD_FILE).unlink()
            self.assertEqual(s.pane_auto_tick(self.root), [self.d.name])
            ap = json.loads((self.d / fb.APPROVE_FILE).read_text(encoding="utf-8"))
            self.assertEqual(ap["line"], s.PANE_AUTO_PHRASES["read"] + f" .aimem/sessions/{self.d.name}/brief.md")
            self.assertIn("자동 전송", ap["by"])
            self.assertEqual(s.pane_auto_tick(self.root), [])                   # 이미 승인이 적혀 있다
            (self.d / fb.APPROVE_FILE).unlink()
            s.pane_auto_set(False, "웹(검사)", self.root)
            self.assertEqual(s.pane_auto_tick(self.root), [])

    def test_auto_phrases_match_the_screen(self):
        js = (pathlib.Path(self.server.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
        for key, text in self.server.PANE_AUTO_PHRASES.items():
            self.assertIn(f"key: '{key}'", js)
            self.assertIn(f"text: '{text}'", js, key)

    def test_refusals(self):
        s = self.server
        self.assertEqual(s.pane_send(self.d.name, {"action": "send", "text": "  "}, "웹", self.root)[0], 400)
        self.assertEqual(s.pane_send(self.d.name, {"action": "send"}, "웹", self.root)[0], 400)
        self.assertEqual(s.pane_send(self.d.name, {"action": "send", "text": "/bash ls"}, "웹", self.root)[0], 400)
        self.assertEqual(s.pane_send(self.d.name, {"action": "x", "text": "해 줘"}, "웹", self.root)[0], 400)
        self.assertEqual(s.pane_send("../x", {"action": "send", "text": "해 줘"}, "웹", self.root)[0], 400)
        self.assertEqual(s.pane_send("T-1-S1-a1-000000", {"action": "send", "text": "해 줘"}, "웹", self.root)[0], 404)
        self.assertFalse((self.d / fb.APPROVE_FILE).exists())
        (self.d / fb.GATE_FILE).write_text(json.dumps({"phase": "sent"}), encoding="utf-8")
        self.assertEqual(s.pane_send(self.d.name, {"action": "send", "text": "새 글"}, "웹", self.root)[0], 409)
        other = self.session("T-901-S1-a1-000000")
        meta = json.loads((other / "meta.json").read_text(encoding="utf-8"))
        meta["harness"] = "claude"
        (other / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(s.pane_send(other.name, {"action": "send", "text": "해 줘"}, "웹", self.root)[0], 404)


if __name__ == "__main__":
    unittest.main()
