"""`tools/fleet_graph.py` 계약 테스트 (T-088, G-005).

표준 라이브러리 unittest + tempfile + subprocess + unittest.mock 만 쓴다.
실제 `.aimem/graph` 와 `.aimem/runs` 는 건드리지 않는다 - `GRAPHS` 와 `RUNS` 를
매 테스트마다 임시 디렉터리로 갈아끼운다. 실제 작업자도 띄우지 않는다.
"""
import argparse
import contextlib
import datetime as dt
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fleet_graph  # noqa: E402
import fleet  # noqa: E402


class FleetGraphContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.graphs = self.tmp / "graph"
        self.runs = self.tmp / "runs"
        self.graphs.mkdir()
        self.runs.mkdir()
        for module, attr, value in (
            (fleet_graph, "GRAPHS", self.graphs),
            (fleet_graph, "_LOGGED_ONCE", set()),
            (fleet, "RUNS", self.runs),
        ):
            patcher = mock.patch.object(module, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for attr, value in (
            ("roster", {"S2": ("d27e93", "codex", "")}),
            ("owned_paths", ["tests/test_fleet_graph.py"]),
            ("_slot_model", None),           # 운영 DB 의 슬롯 모델을 읽지 않게
        ):
            patcher = mock.patch.object(fleet, attr, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # 공급자 점검은 네트워크를 탄다 - 검사에서는 늘 막아 둔다
        for patcher in (mock.patch("fleet_rt.providers.probe", return_value=(True, "검사")),
                        mock.patch.object(fleet_graph, "_PROBE_CACHE", {})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _now(self):
        return dt.datetime.now().isoformat(timespec="seconds")

    def _node(self, node_id="T-1", status="running", deps=None, attempts=None, **extra):
        node = {
            "id": node_id,
            "title": node_id,
            "slot": "S2",
            "task": "계약 테스트용 노드",
            "deps": list(deps or []),
            "write": [],
            "max_attempts": 2,
            "status": status,
            "attempts": list(attempts or []),
        }
        node.update(extra)
        return node

    def _attempt(self, run_id="R-1", started=None):
        return {"run_id": run_id, "started": started or self._now()}

    def _write_run(self, run_id, harness=None, out=None, meta=True):
        if meta:
            (self.runs / f"{run_id}.json").write_text(
                json.dumps({"harness": harness}), encoding="utf-8"
            )
        if out is not None:
            (self.runs / f"{run_id}.out").write_text(out, encoding="utf-8")

    def _graph(self, nodes, **extra):
        graph = {
            "id": "G-900",
            "request": "contract test",
            "created": self._now(),
            "concurrency": 3,
            "nodes": nodes,
        }
        graph.update(extra)
        return graph

    def _save_graph(self, graph):
        (self.graphs / f"{graph['id']}.json").write_text(
            json.dumps(graph, ensure_ascii=False), encoding="utf-8"
        )

    # ---------------------------------------------------------------- (A) 잠금
    def test_graph_lock_excludes_child_process(self):
        with fleet_graph.graph_lock("G-900"):
            script = (
                "import pathlib, sys\n"
                f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
                "import fleet_graph\n"
                f"fleet_graph.GRAPHS = pathlib.Path({str(self.graphs)!r})\n"
                "with fleet_graph.graph_lock('G-900'):\n"
                "    print('acquired')\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", script], capture_output=True, text=True
            )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("다른 실행자가 잡고 있습니다", result.stderr)
        self.assertIn(str(os.getpid()), result.stderr)

    def test_graph_lock_child_can_lock_after_release(self):
        with fleet_graph.graph_lock("G-900"):
            pass
        script = (
            "import pathlib, sys\n"
            f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
            "import fleet_graph\n"
            f"fleet_graph.GRAPHS = pathlib.Path({str(self.graphs)!r})\n"
            "with fleet_graph.graph_lock('G-900'):\n"
            "    print('acquired')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("acquired", result.stdout)

    def test_graph_lock_released_after_runtime_error(self):
        with self.assertRaises(RuntimeError):
            with fleet_graph.graph_lock("G-900"):
                raise RuntimeError("boom")
        with fleet_graph.graph_lock("G-900"):
            pass

    def test_graph_lock_released_after_system_exit(self):
        with self.assertRaises(SystemExit):
            with fleet_graph.graph_lock("G-900"):
                raise SystemExit(3)
        with fleet_graph.graph_lock("G-900"):
            pass

    def test_graph_lock_file_is_not_deleted(self):
        lock_path = self.graphs / "G-900.lock"
        with fleet_graph.graph_lock("G-900"):
            self.assertTrue(lock_path.exists())
        self.assertTrue(lock_path.exists())

    def test_graph_lock_overwrites_stale_content(self):
        lock_path = self.graphs / "G-900.lock"
        lock_path.write_text("x" * 500, encoding="utf-8")
        with fleet_graph.graph_lock("G-900", "step"):
            pass
        holder = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(holder["pid"], os.getpid())
        self.assertIsInstance(holder["pid"], int)
        self.assertIsInstance(holder["started"], str)
        self.assertIsInstance(holder["cmd"], str)
        self.assertEqual(holder["cmd"], "step")
        self.assertIsNotNone(dt.datetime.fromisoformat(holder["started"]))

    def test_graph_lock_rejects_path_separators(self):
        for gid in ("a/b", "..", ""):
            with self.subTest(gid=gid):
                with self.assertRaises((ValueError, SystemExit)):
                    with fleet_graph.graph_lock(gid):
                        pass
                self.assertEqual(list(self.graphs.iterdir()), [])

    # ---------------------------------------------------------------- (B) 보고 첫 줄
    def test_report_block_reason_contract_table(self):
        cases = [
            ("", None),
            (None, None),
            ("   \n\n  ", None),
            ("상태: DONE", None),
            ("PARTIAL", None),
            ("상태: DONE - BLOCKED 되었던 것을 풀었다", None),
            ("DONE (이전 시도는 NEEDS-LOCK)", None),
            ("상태: DONE\nBLOCKED", None),
            ("## 보고\n상태: BLOCKED", None),
            ("Rejected 된 항목 없음, 모두 통과", None),
            ("REJECTED_FIX 적용 완료", None),
            ("Blocked 링크 3개를 풀었다", None),
            ("BLOCKED-FREE 빌드 성공", None),
            ("NEEDS-", None),
            ("BLOCKED", "BLOCKED"),
            ("상태: BLOCKED - 이유", "BLOCKED"),
            ("**NEEDS-LOCK** 경로", "NEEDS-LOCK"),
            ("\n\n# NEEDS-APPROVAL x", "NEEDS-APPROVAL"),
            ("REJECT - y", "REJECT"),
            ("> BLOCKED", "BLOCKED"),
            ("1. BLOCKED", "BLOCKED"),
            ("- BLOCKED", "BLOCKED"),
            ("`BLOCKED`", "BLOCKED"),
            ("[BLOCKED]", "BLOCKED"),
            ("상태: `BLOCKED`", "BLOCKED"),
            ("Status: BLOCKED", "BLOCKED"),
            ("상태: blocked - 소문자", "BLOCKED"),
            # 한 낱말이다. 단어 경계가 막는다.
            ("BLOCKED" + "x" * 100000, None),
            # 낱말 뒤가 공백이라 경계를 통과한다. 아주 긴 줄에도 터지지 않는다.
            ("BLOCKED " + "x" * 100000, "BLOCKED"),
            ("BLOCKED: 소유가 아닌 경로", "BLOCKED"),
        ]
        for report, expected in cases:
            with self.subTest(report=repr(report)[:60], expected=expected):
                self.assertEqual(fleet_graph.report_block_reason(report), expected)

    # ---------------------------------------------------------------- (C) step 완료 판정
    def test_step_blocked_report_with_rc_zero_is_blocked_no_retry(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt])
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 0)), \
             mock.patch.object(fleet, "run_report", return_value="상태: BLOCKED - 이유"):
            fleet_graph.step(graph)
        self.assertEqual(node["status"], "blocked")
        self.assertEqual(len(node["attempts"]), 1)
        self.assertEqual(attempt["report_status"], "BLOCKED")
        self.assertIsNone(attempt["verify_rc"])

    def test_step_done_report_without_verify_is_done(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], verify=None)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 0)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE"):
            fleet_graph.step(graph)
        self.assertEqual(node["status"], "done")
        self.assertEqual(attempt["verify_rc"], 0)

    def test_step_blocked_report_beats_failing_verify(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], verify="false")
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 0)), \
             mock.patch.object(fleet, "run_report", return_value="상태: BLOCKED - 이유"), \
             mock.patch.object(fleet_graph, "_verify") as verify_mock:
            fleet_graph.step(graph)
        self.assertEqual(node["status"], "blocked")
        self.assertNotEqual(node["status"], "failed")
        verify_mock.assert_not_called()
        self.assertIsNone(attempt["verify_rc"])

    def test_report_limit_hit_contract_table(self):
        cases = [
            ("상태: DONE\nClaude hit your 5-hour limit", True),
            ("5-hour limit reached", True),
            ("주간 한도에 걸렸습니다", True),
            ("사용 한도로 끝났습니다", True),
            ("Session limit reached ∙ resets 3pm", True),
            ("You've reached your usage limit", True),
            ("상태: DONE\n- 검증 통과", False),
            ("DONE\n- 함대 탭에 Claude 사용 한도 카드를 넣었습니다", False),
            ("DONE\n- rate limit 글자를 설명에 적었습니다", False),
            ("상태: DONE\n- 주간 한도 표시를 style.css 에 넣었습니다", False),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(fleet_graph.report_limit_hit(text), expected)

    def test_report_limit_hit_ignores_bare_limit_words(self):
        for text in ("상태: DONE\n사용 한도", "사용 한도 카드를 넣었습니다", "주간 한도 표시"):
            with self.subTest(text=text):
                self.assertFalse(fleet_graph.report_limit_hit(text))

    def test_report_limit_hit_ignores_empty_and_non_string(self):
        for text in ("", None, 0, [], {"limit": "사용 한도"}):
            with self.subTest(text=repr(text)):
                self.assertFalse(fleet_graph.report_limit_hit(text))

    def test_report_limit_hit_only_reads_last_2000_chars(self):
        self.assertFalse(fleet_graph.report_limit_hit("5-hour limit reached\n" + "x" * 2500 + "\n상태: DONE"))
        self.assertTrue(fleet_graph.report_limit_hit("x" * 2500 + "\n사용 한도로 끊겼습니다"))

    def test_step_limit_hit_blocks_without_retry(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE\nClaude hit your 5-hour limit"), \
             mock.patch.object(fleet_graph, "_verify") as verify_mock:
            fleet_graph.step(graph)
        self.assertEqual(node["status"], "blocked")
        self.assertEqual(len(node["attempts"]), 1)
        self.assertIs(attempt["limit"], True)
        self.assertEqual(attempt["verify_rc"], -4)
        self.assertIn("사용 한도", attempt["verify_tail"])
        verify_mock.assert_not_called()

    def test_step_limit_like_report_with_passing_verify_is_done(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], verify="true")
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 0)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE\n5-hour limit reached"), \
             mock.patch.object(fleet_graph, "_verify", return_value=(0, "ok")) as verify_mock:
            fleet_graph.step(graph)
        self.assertEqual(node["status"], "done")
        self.assertFalse(attempt.get("limit"))
        self.assertEqual(attempt["verify_rc"], 0)
        verify_mock.assert_called_once_with(node)

    def test_step_limit_like_report_with_failing_verify_is_retried_without_limit(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], verify="true")
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 0)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE\n5-hour limit reached"), \
             mock.patch.object(fleet_graph, "_verify", return_value=(1, "빨강")) as verify_mock:
            fleet_graph.step(graph, allow_spawn=False)
        self.assertEqual(node["status"], "todo")
        self.assertFalse(attempt.get("limit"))
        self.assertEqual(attempt["verify_rc"], 1)
        verify_mock.assert_called_once_with(node)

    def test_step_limit_hit_keeps_attempt_count_at_two(self):
        first = self._attempt("R-1")
        second = self._attempt("R-2")
        node = self._node(attempts=[first, second], max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value="5-hour limit reached"):
            fleet_graph.step(graph)
        self.assertEqual(node["status"], "blocked")
        self.assertEqual(len(node["attempts"]), 2)
        self.assertTrue(second["limit"])

    def test_step_limit_flag_remains_in_saved_graph_json(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE\n사용 한도에 도달했습니다"):
            fleet_graph.step(graph)
        saved = json.loads((self.graphs / "G-900.json").read_text(encoding="utf-8"))
        self.assertIs(saved["nodes"][0]["limit"], True)
        self.assertIs(saved["nodes"][0]["attempts"][-1]["limit"], True)

    def test_step_limit_report_with_rc_zero_is_not_a_limit(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], verify=None, max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 0)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE\n5-hour limit reached"):
            fleet_graph.step(graph)
        self.assertNotEqual(node["status"], "blocked")
        self.assertEqual(node["status"], "done")
        self.assertFalse(attempt.get("limit"))
        self.assertEqual(attempt["verify_rc"], 0)

    def test_step_limit_report_with_rc_nonzero_blocks_with_limit(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], verify="true", max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE\n5-hour limit reached"), \
             mock.patch.object(fleet_graph, "_verify") as verify_mock:
            fleet_graph.step(graph)
        self.assertEqual(node["status"], "blocked")
        self.assertIs(attempt["limit"], True)
        self.assertEqual(attempt["verify_rc"], -4)
        self.assertIn("사용 한도", attempt["verify_tail"])
        verify_mock.assert_not_called()

    def test_step_limit_text_before_last_2000_chars_with_nonzero_rc_is_not_limit(self):
        attempt = self._attempt()
        node = self._node(attempts=[attempt], max_attempts=2)
        graph = self._graph([node])
        report = "5-hour limit reached\n" + "x" * 2500 + "\n상태: DONE"
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value=report):
            fleet_graph.step(graph, allow_spawn=False)
        self.assertEqual(node["status"], "todo")
        self.assertFalse(attempt.get("limit"))
        self.assertEqual(attempt["verify_rc"], -1)

    # ---------------------------------------------------------------- (C2) 구조 신호 판정 (T-254)
    def test_run_limit_signal_claude_api_error_status_429_is_true(self):
        self._write_run("R-1", "claude", json.dumps(
            {"is_error": True, "api_error_status": 429, "terminal_reason": "api_error"}))
        self.assertIs(fleet_graph.run_limit_signal("R-1"), True)

    def test_run_limit_signal_claude_usage_limit_api_error_is_true(self):
        self._write_run("R-1", "claude", json.dumps(
            {"is_error": True, "api_error": "usage_limit_reached"}))
        self.assertIs(fleet_graph.run_limit_signal("R-1"), True)

    def test_run_limit_signal_ignores_limit_words_in_a_done_report(self):
        # 보고 글자에 "한도" 가 있어도 구조 신호(is_error false)가 아니면 False 여야 한다.
        self._write_run("R-1", "claude", json.dumps(
            {"is_error": False, "result": "DONE - 사용 한도 표시 기능을 만들었습니다"}))
        self.assertIs(fleet_graph.run_limit_signal("R-1"), False)

    def test_run_limit_signal_is_none_for_text_only_harnesses(self):
        for run_id, harness in (("R-CODEX", "codex"), ("R-OPEN", "opencode")):
            with self.subTest(harness=harness):
                self._write_run(run_id, harness, "DONE: something")
                self.assertIsNone(fleet_graph.run_limit_signal(run_id))

    def test_run_limit_signal_broken_records_return_none_without_raising(self):
        # JSON 이 아닌 글자
        self._write_run("R-BAD", "claude", "본문은 JSON 이 아니다")
        self.assertIsNone(fleet_graph.run_limit_signal("R-BAD"))
        # JSON 이지만 dict 가 아닌 목록
        self._write_run("R-LIST", "claude", "[1,2,3]")
        self.assertIsNone(fleet_graph.run_limit_signal("R-LIST"))
        # .out 파일 자체가 없음
        self._write_run("R-NOOUT", "claude")
        self.assertIsNone(fleet_graph.run_limit_signal("R-NOOUT"))
        # 메타(.json)가 없음
        self._write_run("R-NOMETA", None,
                        json.dumps({"is_error": True, "api_error_status": 429}), meta=False)
        self.assertIsNone(fleet_graph.run_limit_signal("R-NOMETA"))

    def test_step_nonzero_rc_skips_verify_even_when_verify_would_pass(self):
        # verify="true" 는 반드시 초록이다. 면제가 되면 verify_rc=-1, 안 되면 0 이 된다.
        attempt = self._attempt()
        node = self._node(attempts=[attempt], verify="true", max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE"), \
             mock.patch.object(fleet_graph, "_verify", return_value=(0, "ok")) as verify_mock:
            fleet_graph.step(graph, allow_spawn=False)
        verify_mock.assert_not_called()
        self.assertEqual(attempt["verify_rc"], -1)
        self.assertIn("실행 rc != 0", attempt["verify_tail"])
        self.assertNotEqual(node["status"], "done")
        self.assertEqual(node["status"], "todo")

    def test_step_nonzero_rc_with_structural_limit_blocks_and_logs_limit(self):
        self._write_run("R-LIM", "claude", json.dumps(
            {"is_error": True, "api_error_status": 429, "terminal_reason": "api_error"}))
        attempt = self._attempt("R-LIM")
        node = self._node(attempts=[attempt], verify="true", max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE"), \
             mock.patch.object(fleet_graph, "_verify") as verify_mock:
            fleet_graph.step(graph, allow_spawn=False)
        self.assertEqual(node["status"], "blocked")
        self.assertIs(node["limit"], True)
        self.assertIs(attempt["limit"], True)
        self.assertEqual(attempt["verify_rc"], -4)
        verify_mock.assert_not_called()
        log = (self.graphs / "G-900.log").read_text(encoding="utf-8")
        self.assertIn("limit", log)
        self.assertIn("R-LIM", log)

    def test_step_nonzero_rc_structural_false_ignores_limit_words_in_report(self):
        # is_error false 인 claude JSON 은 구조 신호 False - 보고에 한도 글자가 있어도 보통 실패로 간다.
        self._write_run("R-NOLIM", "claude", json.dumps(
            {"is_error": False, "result": "상태: DONE"}))
        attempt = self._attempt("R-NOLIM")
        node = self._node(attempts=[attempt], verify="true", max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value="상태: DONE\n5-hour limit reached"), \
             mock.patch.object(fleet_graph, "_verify") as verify_mock:
            fleet_graph.step(graph, allow_spawn=False)
        self.assertFalse(node.get("limit"))
        self.assertFalse(attempt.get("limit"))
        self.assertEqual(attempt["verify_rc"], -1)
        self.assertIn("실행 rc != 0", attempt["verify_tail"])
        self.assertNotEqual(node["status"], "blocked")
        self.assertEqual(node["status"], "todo")
        verify_mock.assert_not_called()
        log = (self.graphs / "G-900.log").read_text(encoding="utf-8")
        self.assertNotIn("limit", log)

    # ---------------------------------------------------------------- T-264: 한도 판정 회귀·변이 구멍 (N3~N7, M3~M8)
    _N3 = {"is_error": True, "result": "You've hit your 5-hour limit · resets 11:20am"}

    def _step_rc1(self, run_id, report="상태: DONE", verify="true"):
        attempt = self._attempt(run_id)
        node = self._node(attempts=[attempt], verify=verify, max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)), \
             mock.patch.object(fleet, "run_report", return_value=report), \
             mock.patch.object(fleet_graph, "_verify") as verify_mock:
            fleet_graph.step(graph, allow_spawn=False)
        verify_mock.assert_not_called()
        log = (self.graphs / "G-900.log").read_text(encoding="utf-8")
        return node, attempt, log

    def test_n3_is_error_without_structural_marker_is_none(self):
        self._write_run("R-1", "claude", json.dumps(self._N3))
        self.assertIsNone(fleet_graph.run_limit_signal("R-1"))

    def test_n3_is_error_false_stays_false(self):
        self._write_run("R-1", "claude", json.dumps(
            {"is_error": False, "result": "You've hit your 5-hour limit"}))
        self.assertIs(fleet_graph.run_limit_signal("R-1"), False)

    def test_n3_step_falls_through_to_text_judgement_and_blocks(self):
        # M5: 구조 표지가 없는 오류 기록 + rc != 0 -> 글자 판정이 살아 있어 limit 으로 blocked
        self._write_run("R-N3", "claude", json.dumps(self._N3))
        node, attempt, _log_text = self._step_rc1(
            "R-N3", report="You've hit your 5-hour limit · resets 11:20am")
        self.assertEqual(node["status"], "blocked")
        self.assertIs(node["limit"], True)
        self.assertIs(attempt["limit"], True)
        self.assertEqual(attempt["verify_rc"], -4)

    def test_m3_is_error_false_wins_over_429_and_api_error_markers(self):
        self._write_run("R-1", "claude", json.dumps(
            {"is_error": False, "api_error_status": 429,
             "terminal_reason": "api_error", "result": "limit"}))
        self.assertIs(fleet_graph.run_limit_signal("R-1"), False)

    def test_m4_terminal_reason_api_error_branch_alone_is_true(self):
        self._write_run("R-1", "claude", json.dumps(
            {"is_error": True, "terminal_reason": "api_error",
             "result": "You've hit your 5-hour limit · resets 11:20am"}))
        self.assertIs(fleet_graph.run_limit_signal("R-1"), True)

    def test_n4_context_window_limit_is_not_a_usage_limit(self):
        self._write_run("R-1", "claude", json.dumps(
            {"is_error": True, "terminal_reason": "api_error",
             "result": "Prompt exceeds the context window limit"}))
        self.assertIsNone(fleet_graph.run_limit_signal("R-1"))

    def test_m6_non_claude_harness_ignores_claude_shaped_json(self):
        body = json.dumps({"is_error": True, "api_error_status": 429})
        for run_id, harness in (("R-CODEX", "codex"), ("R-OPEN", "opencode")):
            with self.subTest(harness=harness):
                self._write_run(run_id, harness, body)
                self.assertIsNone(fleet_graph.run_limit_signal(run_id))

    def _session(self, run_id, events):
        root = self.tmp / "sessions"
        d = root / run_id
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"harness_effective": "claude"}), encoding="utf-8")
        (d / "events.jsonl").write_text(
            "".join(f"2026-11-12T10:00:00\t{json.dumps(e)}\n" for e in events), encoding="utf-8")
        p = mock.patch.object(fleet, "_sessions_root", return_value=root)
        p.start()
        self.addCleanup(p.stop)
        # tests/_fleet_env.py 가 AIFLEET_HARNESS=fake 를 깔아 get() 이 늘 fake 를 준다 - 그 안전 장치는
        # 두고, 어댑터 고르기만 claude 어댑터(파일만 읽는다)로 바꾼다.
        from fleet_rt.harness import claude as claude_harness  # noqa: PLC0415
        self.harness_get = mock.Mock(side_effect=lambda name: claude_harness.ADAPTER)
        p2 = mock.patch("fleet_rt.harness.get", self.harness_get)
        p2.start()
        self.addCleanup(p2.stop)

    def _res(self, **kw):
        d = {"type": "result", "subtype": "error", "is_error": True, "session_id": "s1"}
        d.update(kw)
        return d

    def test_q2_session_branch_n3_record_is_none(self):
        self._session("T-1-S1-a1-000000", [self._res(result="You've hit your 5-hour limit")])
        self.assertIsNone(fleet_graph.run_limit_signal("T-1-S1-a1-000000"))

    def test_q2_session_branch_context_window_text_is_not_true(self):
        self._session("T-1-S1-a1-000000", [self._res(
            terminal_reason="api_error", result="Prompt exceeds the context window limit")])
        self.assertIsNone(fleet_graph.run_limit_signal("T-1-S1-a1-000000"))

    def test_fifo_out_does_not_block_and_is_none(self):
        import threading  # noqa: PLC0415
        self._write_run("X", "claude")
        os.mkfifo(self.runs / "X.out")
        box = []
        t = threading.Thread(target=lambda: box.append(fleet_graph.run_limit_signal("X")), daemon=True)
        t.start()
        t.join(3)
        if t.is_alive():
            # 막힌 스레드를 풀어 준다(쓰는 쪽을 열어 줌) - 시험이 남기지 않게
            try:
                fd = os.open(self.runs / "X.out", os.O_WRONLY | os.O_NONBLOCK)
                os.close(fd)
            except OSError:
                pass
            self.fail("run_limit_signal 이 FIFO .out 에서 막혔다")
        self.assertEqual(box, [None])

    def test_oversized_meta_is_none(self):
        (self.runs / "Y.json").write_bytes(b'{"harness": "claude", "pad": "' + b"x" * (2 * 1024 * 1024) + b'"}')
        self.assertIsNone(fleet._run_meta("Y"))

    def test_read_regular_bytes_cases(self):
        f = self.tmp / "f.bin"
        f.write_bytes(b"hello")
        self.assertEqual(fleet.read_regular_bytes(f, 10), b"hello")
        self.assertEqual(fleet.read_regular_bytes(f, 5), b"hello")
        self.assertIsNone(fleet.read_regular_bytes(f, 4))
        self.assertIsNone(fleet.read_regular_bytes(self.tmp, 10))
        self.assertIsNone(fleet.read_regular_bytes(self.tmp / "nope", 10))

    def test_q2_session_branch_429_is_true(self):
        self._session("T-1-S1-a1-000000", [self._res(api_error_status=429)])
        self.assertIs(fleet_graph.run_limit_signal("T-1-S1-a1-000000"), True)
        self.harness_get.assert_called_once_with("claude")

    def test_q1_run_id_with_path_segments_is_none(self):
        self._session("T-1-S1-a1-000000", [self._res(api_error_status=429)])
        root = self.tmp / "sessions"
        outside = self.tmp / "outside" / "evil"
        outside.mkdir(parents=True)
        (outside / "meta.json").write_text(json.dumps({"harness_effective": "claude"}), encoding="utf-8")
        (outside / "events.jsonl").write_text(
            "2026-11-12T10:00:00\t" + json.dumps(self._res(api_error_status=429)) + "\n", encoding="utf-8")
        bad = "T-1-S1-a1-000000/../../outside/evil"
        # 정규식이 `/` 를 허용하면 이 경로가 실제로 풀려 True 가 나온다 - 풀리는 것부터 확인한다.
        self.assertTrue((root / bad / "meta.json").exists())
        self.assertTrue(fleet._session_dir(bad) is not None)
        self.assertIs(fleet_graph.run_limit_signal("T-1-S1-a1-000000"), True)
        for b in (bad, "T-1-S1-a1-000000/../x"):
            with self.subTest(run_id=b):
                self.assertIsNone(fleet_graph.run_limit_signal(b))

    def test_m7_read_is_capped_at_one_mib(self):
        head = '{"is_error": true, "api_error_status": 429'
        # 끝까지 읽으면 올바른 JSON(True), 1 MiB 에서 자르면 깨진 JSON(None)
        pad = ', "pad": "' + "x" * (1024 * 1024 + 4096) + '"}'
        self._write_run("R-BIG", "claude", head + pad)
        self.assertGreater((self.runs / "R-BIG.out").stat().st_size, 1024 * 1024)
        self.assertIsNone(fleet_graph.run_limit_signal("R-BIG"))

    def test_m8_log_marks_structural_source(self):
        self._write_run("R-S", "claude", json.dumps(
            {"is_error": True, "api_error_status": 429, "terminal_reason": "api_error"}))
        node, _att, log = self._step_rc1("R-S")
        self.assertEqual(node["status"], "blocked")
        self.assertIn("(구조 신호)", log)
        self.assertNotIn("(보고 글자)", log)

    def test_m8_log_marks_report_text_source(self):
        self._write_run("R-T", "claude", json.dumps(self._N3))
        node, _att, log = self._step_rc1("R-T", report="You've hit your weekly limit")
        self.assertEqual(node["status"], "blocked")
        self.assertIn("(보고 글자)", log)
        self.assertNotIn("(구조 신호)", log)

    def test_n5_report_limit_hit_rejects_non_limit_reports(self):
        self.assertIs(fleet_graph.report_limit_hit(
            "NEEDS-FIX: verify step time limit reached, test failed"), False)
        self.assertIs(fleet_graph.report_limit_hit(
            "DONE - added handler for HTTP 429 Too Many Requests"), False)

    def test_n5_report_limit_hit_accepts_weekly_limit(self):
        self.assertIs(fleet_graph.report_limit_hit("You've hit your weekly limit"), True)

    def test_n7_run_id_escaping_runs_dir_is_none(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "evil.json").write_text(json.dumps({"harness": "claude"}), encoding="utf-8")
        (outside / "evil.out").write_text(
            json.dumps({"is_error": True, "api_error_status": 429}), encoding="utf-8")
        self.assertIsNone(fleet_graph.run_limit_signal("../outside/evil"))

    def test_n7_non_string_run_id_is_none(self):
        for bad in (None, 123, ["R-1"], b"R-1", {"a": 1}):
            with self.subTest(run_id=bad):
                self.assertIsNone(fleet_graph.run_limit_signal(bad))

    def test_cmd_status_marks_limit_nodes(self):
        node = self._node(status="blocked", attempts=[self._attempt()])
        node["limit"] = True
        self._save_graph(self._graph([node]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fleet_graph.cmd_status(argparse.Namespace(id="G-900"))
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("(사용 한도)", out)
        self.assertIn('"limit": true', out)

    def test_step_dependents_of_blocked_node_become_blocked(self):
        blocked = self._node("T-1", status="blocked", attempts=[self._attempt()])
        blocked["attempts"][0].update({"rc": 0, "state": "done", "report_status": "BLOCKED"})
        dependent = self._node("T-2", status="todo", deps=["T-1"])
        graph = self._graph([blocked, dependent])
        fleet_graph.step(graph)
        self.assertEqual(dependent["status"], "blocked")

    # ---------------------------------------------------------------- (D) 노드 타임아웃
    def test_node_timeout_selection_order(self):
        cases = [
            ({"timeout_sec": 7}, {"node_timeout_sec": 20}, 7.0),
            ({}, {"node_timeout_sec": 20}, 20.0),
            ({}, {}, float(fleet_graph.DEFAULT_NODE_TIMEOUT_SEC)),
        ]
        for node_extra, graph_extra, expected in cases:
            with self.subTest(node=node_extra, graph=graph_extra, expected=expected):
                node = self._node(**node_extra)
                graph = self._graph([node], **graph_extra)
                self.assertEqual(fleet_graph._node_timeout(graph, node), expected)

    def test_node_timeout_discards_invalid_values_and_spares_fresh_worker(self):
        invalid = [float("nan"), 0, -1, True, "abc"]
        for value in invalid:
            with self.subTest(value=repr(value)):
                node = self._node(timeout_sec=value)
                graph = self._graph([node], node_timeout_sec=60)
                self.assertEqual(fleet_graph._node_timeout(graph, node), 60.0)

                attempt = self._attempt(
                    started=(dt.datetime.now() - dt.timedelta(seconds=1)).isoformat(timespec="seconds")
                )
                fresh = self._node(attempts=[attempt], timeout_sec=value)
                fresh_graph = self._graph([fresh], node_timeout_sec=60)
                with mock.patch.object(fleet_graph, "_kill_run") as kill_mock:
                    handled = fleet_graph._check_timeout(fresh_graph, fresh, attempt)
                self.assertFalse(handled)
                kill_mock.assert_not_called()

                default_node = self._node(timeout_sec=value)
                default_graph = self._graph([default_node])
                self.assertEqual(
                    fleet_graph._node_timeout(default_graph, default_node),
                    float(fleet_graph.DEFAULT_NODE_TIMEOUT_SEC),
                )

    def test_timeout_marks_attempt_and_retries_within_limit(self):
        attempt = self._attempt(
            started=(dt.datetime.now() - dt.timedelta(seconds=1000)).isoformat(timespec="seconds")
        )
        node = self._node(attempts=[attempt], timeout_sec=10, max_attempts=2)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet_graph, "_kill_run", return_value=(4242, "killed")) as kill_mock, \
             mock.patch.object(fleet_graph, "_spawn_node"):
            fleet_graph.step(graph)
        kill_mock.assert_called_once_with(attempt["run_id"], with_outcome=True)
        self.assertEqual(attempt["rc"], 124)
        self.assertEqual(attempt["state"], "timeout")
        self.assertIs(attempt["timeout"], True)
        self.assertTrue((self.runs / f"{attempt['run_id']}.lost").exists())
        self.assertEqual(node["status"], "todo")

    def test_timeout_marks_failed_past_attempt_limit(self):
        attempt = self._attempt(
            started=(dt.datetime.now() - dt.timedelta(seconds=1000)).isoformat(timespec="seconds")
        )
        node = self._node(attempts=[attempt], timeout_sec=10, max_attempts=1)
        graph = self._graph([node])
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet_graph, "_kill_run", return_value=(4242, "killed")), \
             mock.patch.object(fleet_graph, "_spawn_node"):
            fleet_graph.step(graph)
        self.assertEqual(attempt["rc"], 124)
        self.assertEqual(node["status"], "failed")

    def test_timeout_does_not_overwrite_existing_lost_marker(self):
        attempt = self._attempt(
            started=(dt.datetime.now() - dt.timedelta(seconds=1000)).isoformat(timespec="seconds")
        )
        node = self._node(attempts=[attempt], timeout_sec=10)
        graph = self._graph([node])
        lost = self.runs / f"{attempt['run_id']}.lost"
        original = json.dumps({"ended": "2026-11-10T01:02:03"})
        lost.write_text(original, encoding="utf-8")
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet_graph, "_kill_run", return_value=(4242, "killed")), \
             mock.patch.object(fleet_graph, "_spawn_node"):
            fleet_graph.step(graph)
        self.assertEqual(lost.read_text(encoding="utf-8"), original)
        self.assertEqual(json.loads(lost.read_text(encoding="utf-8")),
                         {"ended": "2026-11-10T01:02:03"})

    def test_broken_started_does_not_raise_or_kill(self):
        for started in ("garbage", None, "", "2026-11-10T09:00:00+09:00"):
            with self.subTest(started=repr(started)):
                attempt = {"run_id": "R-1", "started": started}
                node = self._node(attempts=[attempt])
                graph = self._graph([node], node_timeout_sec=10 ** 9)
                with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
                     mock.patch.object(fleet_graph, "_kill_run") as kill_mock:
                    fleet_graph.step(graph)
                    fleet_graph.progress(graph)
                kill_mock.assert_not_called()

    # ---------------------------------------------------------------- (E) 시작 전 모양 검증
    def test_cmd_step_and_run_reject_malformed_dag_without_spawn(self):
        malformed = {
            "cycle": [
                self._node("T-1", status="todo", deps=["T-2"]),
                self._node("T-2", status="todo", deps=["T-1"]),
            ],
            "unknown_dep": [
                self._node("T-1", status="todo", deps=["T-9"]),
            ],
        }
        for name, nodes in malformed.items():
            for command in ("step", "run"):
                with self.subTest(case=name, command=command):
                    graph = self._graph(nodes)
                    self._save_graph(graph)
                    args = argparse.Namespace(id=graph["id"], concurrency=None)
                    if command == "run":
                        args.timeout = 3600
                        args.poll = 10
                    with mock.patch.object(fleet, "cmd_spawn") as spawn_mock:
                        with contextlib.redirect_stdout(io.StringIO()), \
                             contextlib.redirect_stderr(io.StringIO()):
                            rc = (fleet_graph.cmd_step if command == "step" else fleet_graph.cmd_run)(args)
                    self.assertEqual(rc, 2)
                    spawn_mock.assert_not_called()

    def test_cmd_step_allows_finished_graph_with_unknown_slot(self):
        node = self._node("T-1", status="done")
        node["slot"] = "S9"
        graph = self._graph([node])
        self._save_graph(graph)
        args = argparse.Namespace(id=graph["id"], concurrency=None)
        with mock.patch.object(fleet, "cmd_spawn") as spawn_mock:
            with contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                rc = fleet_graph.cmd_step(args)
        self.assertEqual(rc, 0)
        spawn_mock.assert_not_called()

    def test_validate_graph_rejects_bad_project_name(self):
        good, bad = self._node("T-1"), self._node("T-2")
        good["project"] = "reefwiz-앱"
        bad["project"] = "../../etc"
        problems = fleet_graph.validate_graph(self._graph([good, bad]))
        self.assertTrue(any(p.startswith("T-2:") and "project" in p for p in problems))
        self.assertFalse(any(p.startswith("T-1:") and "project" in p for p in problems))

    def test_validate_graph_default_still_checks_done_node_slot(self):
        node = self._node("T-1", status="done")
        node["slot"] = "S9"
        graph = self._graph([node])
        problems = fleet_graph.validate_graph(graph)
        self.assertTrue(any("S9" in problem and "명부" in problem for problem in problems))

    # ---------------------------------------------------------------- (F) 실제 `_kill_run` (S4 3차 검수 커버리지 표 - 결함 1·2·10)
    def _meta(self, run_id, pid):
        (self.runs / f"{run_id}.json").write_text(json.dumps({"pid": pid, "slot": "S2", "harness": "codex"}),
                                                 encoding="utf-8")

    def _spawn_group(self, script):
        """`fleet.py spawn` 과 같은 모양 - 새 세션의 `sh -c` 래퍼 + 자식. cmdline 에 `fleet` 이 들어 있다."""
        proc = subprocess.Popen(["sh", "-c", script + "  # fleet-test"], start_new_session=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self._reap, proc)
        return proc

    @staticmethod
    def _reap(proc):
        try:
            os.killpg(proc.pid, 9)
        except OSError:
            pass
        proc.wait(timeout=5)

    def _children(self, pid, want, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            kids = [int(x) for x in subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()]
            if len(kids) >= want:
                return kids
            time.sleep(0.05)
        self.fail(f"자식 프로세스 {want}개가 뜨지 않았다")

    def test_kill_run_kills_wrapper_and_its_child(self):
        # 결함 1: 래퍼만 죽이면 실제 작업자(자식)가 고아로 살아 계속 쓴다 -> 그룹 전체가 죽어야 한다.
        proc = self._spawn_group("sleep 300 & wait")
        child = self._children(proc.pid, 1)[0]
        self._meta("R-K", proc.pid)
        t0 = time.time()
        self.assertEqual(fleet_graph._kill_run("R-K", with_outcome=True), (proc.pid, "killed"))
        self.assertLess(time.time() - t0, fleet_graph.KILL_GRACE_SEC - 1)   # 결함 10: 좀비 래퍼 때문에 유예를 다 쓰지 않는다
        proc.wait(timeout=5)
        deadline = time.time() + 3
        while time.time() < deadline and os.path.exists(f"/proc/{child}"):
            time.sleep(0.05)
        self.assertFalse(os.path.exists(f"/proc/{child}"), "자식(실제 작업자)이 살아 남았다")

    def test_pgroup_alive_sees_child_behind_zombie_leader(self):
        # 결함 10: 리더가 좀비여도 자식이 살아 있으면 살아 있는 그룹이고, 자식도 없으면 죽은 그룹이다.
        proc = self._spawn_group("sleep 300 & exit 0")       # 리더는 곧 끝나 (거두지 않은) 좀비가 된다
        deadline = time.time() + 5
        while time.time() < deadline and fleet_graph._proc_state(proc.pid) != "Z":
            time.sleep(0.05)
        self.assertEqual(fleet_graph._proc_state(proc.pid), "Z")
        self.assertTrue(fleet_graph._pgroup_alive(proc.pid))
        os.killpg(proc.pid, 9)
        deadline = time.time() + 5
        while time.time() < deadline and fleet_graph._pgroup_alive(proc.pid):
            time.sleep(0.05)
        self.assertFalse(fleet_graph._pgroup_alive(proc.pid))

    def test_kill_run_refuses_unsafe_pids_without_signalling(self):
        # 결함 2: 안전 검사가 하나라도 어긋나면 아무에게도 신호를 보내지 않는다.
        bystander = subprocess.Popen(["sleep", "300"])       # 내 프로세스 그룹 안, 세션 리더 아님
        self.addCleanup(lambda: (bystander.kill(), bystander.wait(timeout=5)))
        cases = [None, True, False, 0, 1, -5, os.getpid(), "123", 1.5, bystander.pid]
        with mock.patch.object(fleet_graph.os, "killpg") as killpg, mock.patch.object(fleet_graph.os, "kill") as kill:
            for i, pid in enumerate(cases):
                with self.subTest(pid=repr(pid)):
                    self._meta(f"R-U{i}", pid)
                    self.assertEqual(fleet_graph._kill_run(f"R-U{i}", with_outcome=True), (pid, "refused"))
                    self.assertTrue(fleet_graph._LAST_REFUSAL.get(f"R-U{i}"))
            self._meta("R-GONE", 2 ** 22 + 12345)            # 없는 pid 는 refused 가 아니라 gone
            self.assertEqual(fleet_graph._kill_run("R-GONE", with_outcome=True)[1], "gone")
            killpg.assert_not_called()
            kill.assert_not_called()
        self.assertIsNone(bystander.poll())

    def test_kill_run_spares_foreign_process_with_reused_pid(self):
        # 결함 2: pid 가 재사용돼 그 실행과 무관한 세션 리더를 가리키면 죽이지 않는다.
        proc = subprocess.Popen(["sleep", "300"], start_new_session=True)
        self.addCleanup(self._reap, proc)
        self._meta("R-F", proc.pid)
        self.assertEqual(fleet_graph._kill_run("R-F", with_outcome=True), (proc.pid, "foreign"))
        self.assertIsNone(proc.poll())

    # ---------------------------------------------------------------- (G) refused -> blocked (결함 7) / unblock (결함 11)
    def _timed_out_graph(self, **node_extra):
        attempt = self._attempt(started=(dt.datetime.now() - dt.timedelta(seconds=1000)).isoformat(timespec="seconds"))
        node = self._node(attempts=[attempt], timeout_sec=10, **node_extra)
        after = self._node("T-2", status="todo", deps=["T-1"])
        return attempt, node, after, self._graph([node, after])

    def test_refused_kill_blocks_node_without_lost_marker_or_respawn(self):
        attempt, node, after, graph = self._timed_out_graph()
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet_graph, "_kill_run", return_value=(4242, "refused")), \
             mock.patch.object(fleet_graph, "_spawn_node") as spawn:
            fleet_graph.step(graph, allow_spawn=True)
            fleet_graph.step(graph, allow_spawn=True)
        self.assertEqual(node["status"], "blocked")
        self.assertEqual(attempt["kill_outcome"], "refused")
        self.assertNotIn("rc", attempt)
        self.assertFalse((self.runs / f"{attempt['run_id']}.lost").exists(), ".lost 가 생기면 슬롯이 비어 옆에 또 띄운다")
        self.assertEqual(after["status"], "blocked")
        spawn.assert_not_called()

    def test_unblock_refuses_while_worker_alive_then_reaps_finished_run(self):
        attempt, node, after, graph = self._timed_out_graph()
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet_graph, "_kill_run", return_value=(4242, "refused")):
            fleet_graph.step(graph, allow_spawn=False)
            ok, msg = fleet_graph.unblock(graph, "T-1")
        self.assertFalse(ok)
        self.assertIn("살아", msg)
        self.assertEqual(node["status"], "blocked")
        # 작업자가 그 뒤 스스로 끝났다 - 새로 띄우지 않고 그 결과를 거둔다.
        (self.runs / f"{attempt['run_id']}.rc").write_text("0\n", encoding="utf-8")
        ok, msg = fleet_graph.unblock(graph, "T-1")
        self.assertTrue(ok, msg)
        self.assertEqual((node["status"], after["status"]), ("running", "todo"))
        with mock.patch.object(fleet, "run_report", return_value="상태: DONE\n"), \
             mock.patch.object(fleet_graph, "_spawn_node") as spawn:
            fleet_graph.step(graph, allow_spawn=False)
        self.assertEqual(node["status"], "done")
        self.assertEqual(len(node["attempts"]), 1)
        spawn.assert_not_called()

    def test_unblock_requeues_blocked_report_past_attempt_limit_and_frees_dependents(self):
        attempt = dict(self._attempt(), ended=self._now(), rc=0, state="done", report_status="BLOCKED")
        node = self._node(status="blocked", attempts=[attempt], max_attempts=1)
        mid = self._node("T-2", status="blocked", deps=["T-1"])
        leaf = self._node("T-3", status="blocked", deps=["T-2"])
        other = self._node("T-9", status="blocked", attempts=[dict(attempt, run_id="R-9")])
        tail = self._node("T-10", status="blocked", deps=["T-9"])
        graph = self._graph([node, mid, leaf, other, tail])
        (self.runs / "R-1.rc").write_text("0\n", encoding="utf-8")
        self.assertEqual(fleet_graph.unblock(graph, "T-2")[0], False)      # 의존 때문에 막힌 노드는 원인을 풀어야
        self.assertEqual(fleet_graph.unblock(graph, "없음")[0], False)
        ok, msg = fleet_graph.unblock(graph, "T-1")
        self.assertTrue(ok, msg)
        self.assertEqual([n["status"] for n in graph["nodes"]], ["todo", "todo", "todo", "blocked", "blocked"])
        self.assertEqual(node["max_attempts"], 2)                          # 한도를 다 썼어도 한 번 더
        self.assertEqual(fleet_graph.unblock(graph, "T-1")[0], False)      # 이미 todo

    def test_cmd_unblock_saves_graph_and_reports_rc(self):
        attempt = dict(self._attempt(), ended=self._now(), rc=1, state="done")
        self._save_graph(self._graph([self._node(status="failed", attempts=[attempt])]))
        (self.runs / "R-1.rc").write_text("1\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            self.assertEqual(fleet_graph.cmd_unblock(argparse.Namespace(id="G-900", node="T-1")), 0)
            self.assertEqual(fleet_graph.cmd_unblock(argparse.Namespace(id="G-900", node="T-1")), 2)
        saved = json.loads((self.graphs / "G-900.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["nodes"][0]["status"], "todo")
        self.assertIn("unblock T-1", (self.graphs / "G-900.log").read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- (H) tz 변환 (결함 8) / 깨진 run 메타 (큐 2)
    def test_elapsed_converts_timezone_instead_of_dropping_it(self):
        # 같은 순간을 여러 tz 로 적어도 경과는 같아야 한다. tz 를 그냥 떼던 옛 구현은 로컬 tz 가 아닌 표기에서 몇 시간씩 어긋난다.
        moment = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=7200)
        for hours in (0, 9, -5, 14, -3.5):
            with self.subTest(offset=hours):
                txt = moment.astimezone(dt.timezone(dt.timedelta(hours=hours))).isoformat(timespec="seconds")
                self.assertAlmostEqual(fleet_graph._elapsed_since(txt), 7200, delta=5)
        self.assertAlmostEqual(fleet_graph._elapsed_since(moment.strftime("%Y-%m-%dT%H:%M:%SZ")), 7200, delta=5)
        naive_local = moment.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
        self.assertAlmostEqual(fleet_graph._elapsed_since(naive_local), 7200, delta=5)

    def test_fresh_worker_with_utc_started_is_not_killed(self):
        # 결함 8 의 실제 피해: UTC 로 적힌 '방금' 이 로컬로 읽혀 9시간 지난 것으로 보이고 첫 틱에 죽었다.
        attempt = self._attempt(started=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        node = self._node(attempts=[attempt], timeout_sec=600)
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet_graph, "_kill_run") as kill_mock:
            fleet_graph.step(self._graph([node]), allow_spawn=False)
        kill_mock.assert_not_called()
        self.assertEqual(node["status"], "running")

    def test_broken_run_meta_does_not_break_progress_or_run_state(self):
        good_start = (dt.datetime.now() - dt.timedelta(seconds=60)).isoformat(timespec="seconds")
        for rid, meta in (("R-STR", {"pid": "abc", "harness": "codex", "started": good_start}),
                          ("R-NEG", {"pid": -1, "harness": "codex"}),
                          ("R-BOOL", {"pid": True}),
                          ("R-HARNESS", {"pid": 1, "harness": ["x"], "started": good_start}),
                          ("R-OK", {"pid": 1, "harness": "codex", "started": good_start})):
            (self.runs / f"{rid}.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.runs / "R-OK.rc").write_text("0\n", encoding="utf-8")
        (self.runs / "R-HARNESS.rc").write_text("0\n", encoding="utf-8")
        for rid in ("R-STR", "R-NEG", "R-BOOL"):
            self.assertEqual(fleet._run_state(rid), ("unknown", None))     # 예전: TypeError / 그룹에 신호
        durations = fleet_graph.harness_durations()
        self.assertEqual(len(durations["codex"]), 1)
        graph = self._graph([self._node(status="todo")])
        self.assertIn("percent", fleet_graph.progress(graph))
        self.assertEqual(fleet_graph._busy_slots(graph), set())



class EngineV2Stage3(unittest.TestCase):
    """엔진 v2 3단계: 실패의 종류(5.3)·공급자 문지기(5.4)·싼 틱(5.7)·보드 동기화(5.8). 상태는 패치로 꾸민다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.graphs, self.runs = self.tmp / "graph", self.tmp / "runs"
        self.graphs.mkdir()
        self.runs.mkdir()
        for target, attr, value in ((fleet_graph, "GRAPHS", self.graphs), (fleet_graph, "_LOGGED_ONCE", set()),
                                    (fleet_graph, "_PROBE_CACHE", {}), (fleet, "RUNS", self.runs)):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        for attr, value in (("roster", {"S1": ("a", "codex", ""), "S2": ("b", "codex", "")}),
                            ("owned_paths", []), ("_slot_model", None)):
            p = mock.patch.object(fleet, attr, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch("fleet_rt.providers.probe", return_value=(True, "검사"))
        self.probe = p.start()
        self.addCleanup(p.stop)

    def node(self, nid="T-1", status="running", run="R-1", **kw):
        n = {"id": nid, "title": nid, "slot": "S2", "task": "t", "deps": [], "write": [], "max_attempts": 2,
             "status": status, "attempts": ([{"run_id": run, "started": dt.datetime.now().isoformat(timespec="seconds")}]
                                            if status == "running" else [])}
        n.update(kw)
        return n

    def graph(self, nodes):
        return {"id": "G-900", "request": "t", "created": "2026-11-13T00:00:00", "concurrency": 3, "nodes": nodes}

    def reap(self, g, sinfo, state=("done", 1), report=""):
        with mock.patch.object(fleet, "_run_state", return_value=state), \
             mock.patch.object(fleet, "run_report", return_value=report), \
             mock.patch.object(fleet, "_run_meta", return_value={"provider": "kisti"}), \
             mock.patch.object(fleet_graph, "_session_end", return_value=sinfo), \
             mock.patch.object(fleet_graph, "run_limit_signal", return_value=None):
            fleet_graph.step(g, allow_spawn=False)

    # ---- 5.3 실패의 종류
    def test_session_fail_kind_table(self):
        f = fleet_graph.session_fail_kind
        cases = [(None, False, None),
                 ({"state": "stalled", "fail_kind": "infra"}, False, "infra"),
                 ({"state": "failed", "fail_kind": "infra"}, False, "infra"),
                 ({"state": "lost", "fail_kind": None}, False, "infra"),
                 ({"state": "killed", "fail_kind": None}, True, "infra"),     # 실행기가 고아를 끊음
                 ({"state": "killed", "fail_kind": None}, False, None),       # 사람이 끊음 - 보통 실패
                 ({"state": "timeout", "fail_kind": "timeout"}, False, "timeout"),
                 ({"state": "failed", "fail_kind": None}, False, None),
                 ({"state": "failed", "fail_kind": "limit"}, False, None),
                 ({"state": "done", "fail_kind": None}, False, None)]
        for sinfo, cut, want in cases:
            with self.subTest(sinfo=sinfo, cut=cut):
                self.assertEqual(f(sinfo, cut), want)

    def test_stalled_session_is_infra_and_does_not_consume_an_attempt(self):
        n = self.node(max_attempts=1)
        g = self.graph([n])
        self.reap(g, {"state": "stalled", "fail_kind": "infra", "why": "침묵 240초 넘김"}, ("done", 125))
        self.assertEqual(n["status"], "todo")
        self.assertEqual(n["attempts"], [])
        att = n["infra_attempts"][0]
        self.assertEqual((att["fail_kind"], att["session_state"], att["provider"], att["rc"]),
                         ("infra", "stalled", "kisti", 125))
        self.assertIn("침묵", att["why"])
        self.assertNotIn("infra", n)
        saved = json.loads((self.graphs / "G-900.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["nodes"][0]["infra_attempts"][0]["fail_kind"], "infra")

    def test_three_infra_failures_block_with_infra_flag(self):
        n = self.node(status="todo", max_attempts=5)
        g = self.graph([n])
        for k in range(1, fleet_graph.INFRA_RETRY_MAX + 1):
            n["status"] = "running"
            n["attempts"].append({"run_id": f"R-{k}", "started": dt.datetime.now().isoformat(timespec="seconds")})
            self.reap(g, {"state": "failed", "fail_kind": "infra", "why": "재접속"}, ("done", 1))
        self.assertEqual(n["status"], "blocked")
        self.assertIs(n["infra"], True)
        self.assertIs(n["infra_attempts"][-1]["infra"], True)
        self.assertEqual(len(n["infra_attempts"]), 3)
        self.assertEqual(n["attempts"], [])
        log = (self.graphs / "G-900.log").read_text(encoding="utf-8")
        self.assertIn("INFRA T-1 - 공급자 kisti", log)
        self.assertIn("unblock G-900 T-1", log)
        st = fleet_graph._status_node(n)
        self.assertEqual((st["infra"], st["infra_attempts"], st["note"]), (True, 3, "(공급자 장애)"))
        # 사람이 풀면 장애 횟수를 비운다
        with mock.patch.object(fleet, "_run_state", return_value=("done", 1)):
            ok, msg = fleet_graph.unblock(g, "T-1")
        self.assertTrue(ok, msg)
        self.assertEqual((n["status"], fleet_graph._infra_count(n)), ("todo", 0))
        self.assertNotIn("infra", n)

    def test_supervisor_lost_session_is_infra_but_legacy_lost_is_work(self):
        n = self.node()
        self.reap(self.graph([n]), {"state": "lost", "fail_kind": None, "why": "감독 사라짐"}, ("lost", None))
        self.assertEqual((n["status"], len(n.get("infra_attempts", []))), ("todo", 1))
        n2 = self.node()
        self.reap(self.graph([n2]), None, ("lost", None))           # 옛 실행: 감독 판정 없음
        self.assertEqual((n2["status"], n2["attempts"][0]["fail_kind"]), ("todo", "work"))
        self.assertNotIn("infra_attempts", n2)

    def test_work_timeout_limit_and_success_kinds(self):
        n = self.node(max_attempts=1)
        self.reap(self.graph([n]), {"state": "failed", "fail_kind": None}, ("done", 2), "DONE?\n중간에 실패")
        self.assertEqual((n["status"], n["attempts"][0]["fail_kind"]), ("failed", "work"))
        n = self.node(max_attempts=1)
        self.reap(self.graph([n]), {"state": "timeout", "fail_kind": "timeout"}, ("done", 124))
        self.assertEqual((n["status"], n["attempts"][0]["fail_kind"]), ("failed", "timeout"))
        n = self.node(max_attempts=3)
        self.reap(self.graph([n]), None, ("done", 1), "You've hit your usage limit")
        self.assertEqual((n["status"], n["attempts"][0]["fail_kind"]), ("blocked", "limit"))
        n = self.node(max_attempts=3)
        self.reap(self.graph([n]), {"state": "done", "fail_kind": None}, ("done", 0), "BLOCKED: 키 없음")
        self.assertEqual((n["status"], n["attempts"][0]["fail_kind"]), ("blocked", "work"))
        n = self.node()
        self.reap(self.graph([n]), {"state": "done", "fail_kind": None}, ("done", 0), "DONE")
        self.assertEqual(n["status"], "done")
        self.assertIn("fail_kind", n["attempts"][0])
        self.assertIsNone(n["attempts"][0]["fail_kind"])

    def test_wall_clock_timeout_marks_fail_kind(self):
        n = self.node(max_attempts=2, timeout_sec=1)
        n["attempts"][0]["started"] = (dt.datetime.now() - dt.timedelta(seconds=60)).isoformat(timespec="seconds")
        with mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet_graph, "_kill_run", return_value=(4242, "killed")):
            fleet_graph.step(self.graph([n]), allow_spawn=False)
        self.assertEqual((n["status"], n["attempts"][0]["fail_kind"]), ("todo", "timeout"))

    # ---- 5.4 공급자 문지기
    def _spawn_tick(self, g, by_prov, cap=1, busy=()):
        cfg = mock.Mock()
        cfg.max_concurrent.side_effect = lambda p: cap
        spawned = []

        def fake_spawn(g_, n, a):
            n.setdefault("attempts", []).append({"run_id": f"{n['id']}-a{a}", "started": "2026-11-13T00:00:00"})
            n["status"] = "running"
            spawned.append(n["id"])
        with mock.patch.object(fleet_graph, "_live_scan", return_value=(set(busy), dict(by_prov))), \
             mock.patch.object(fleet_graph, "_rt_cfg", return_value=cfg), \
             mock.patch.object(fleet_graph, "_node_provider", side_effect=lambda c, n: n.get("prov", "kisti")), \
             mock.patch.object(fleet_graph, "_spawn_node", side_effect=fake_spawn), \
             mock.patch.object(fleet, "_run_state", return_value=("running", None)), \
             mock.patch.object(fleet, "_session_orphaned", return_value=False), \
             mock.patch.object(fleet_graph, "_check_timeout", return_value=False):
            fleet_graph.step(g, allow_spawn=True)     # 띄운 노드는 계속 도는 것으로 둔다
        return spawned

    def test_provider_full_waits_and_logs_once(self):
        a, b = self.node("T-1", "todo", slot="S1"), self.node("T-2", "todo", slot="S2")
        g = self.graph([a, b])
        self.assertEqual(self._spawn_tick(g, {}), ["T-1"])
        self.assertEqual(b["waiting"], "provider:kisti")
        self.assertEqual(self._spawn_tick(g, {"kisti": 1}), [])
        self.assertEqual(self._spawn_tick(g, {"kisti": 1}), [])
        log = (self.graphs / "G-900.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("wait T-2 - provider:kisti"), 1)
        # 자리가 나면 뜨고 대기 표시가 지워진다
        a["status"] = "done"
        self.assertEqual(self._spawn_tick(g, {"kisti": 0}), ["T-2"])
        self.assertNotIn("waiting", b)

    def test_room_two_spawns_both_and_unknown_provider_is_not_gated(self):
        g = self.graph([self.node("T-1", "todo", slot="S1"), self.node("T-2", "todo", slot="S2")])
        self.assertEqual(self._spawn_tick(g, {}, cap=2), ["T-1", "T-2"])
        g = self.graph([self.node("T-1", "todo", slot="S1", prov=None), self.node("T-2", "todo", slot="S2", prov=None)])
        self.assertEqual(self._spawn_tick(g, {"kisti": 9}), ["T-1", "T-2"])

    def test_dependents_first_then_graph_order(self):
        g = self.graph([self.node("T-1", "todo", slot="S1"), self.node("T-2", "todo", slot="S2"),
                        self.node("T-3", "todo", slot="S1", deps=["T-2"])])
        self.assertEqual(self._spawn_tick(g, {}), ["T-2"])
        g = self.graph([self.node("T-1", "todo", slot="S1"), self.node("T-2", "todo", slot="S2")])
        self.assertEqual(self._spawn_tick(g, {}), ["T-1"])                      # 같으면 그래프 순서

    def test_busy_slot_waits_without_per_tick_log(self):
        a = self.node("T-1", "todo", slot="S2")
        g = self.graph([a])
        for _ in range(3):
            self.assertEqual(self._spawn_tick(g, {}, busy={"S2"}), [])
        self.assertEqual(a["waiting"], "slot:S2")
        log = (self.graphs / "G-900.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("wait T-1 - slot:S2"), 1)
        self.assertNotIn("skip", log)

    def test_probe_gates_only_nodes_with_infra_attempts_and_is_cached(self):
        a = self.node("T-1", "todo", slot="S1", infra_attempts=[{"run_id": "R-0", "fail_kind": "infra"}])
        b = self.node("T-2", "todo", slot="S2", prov="other")
        g = self.graph([a, b])
        self.probe.return_value = (False, "시간 초과 (10초)")
        self.assertEqual(self._spawn_tick(g, {}, cap=3), ["T-2"])
        self.assertEqual(a["waiting"], "probe:kisti")
        self.assertEqual(self._spawn_tick(g, {}, cap=3), [])
        self.assertEqual(self.probe.call_count, 1)                               # 캐시
        self.probe.return_value = (True, "GET /models 200 (응답함)")
        with mock.patch.object(fleet_graph, "PROBE_TTL_SEC", 0.0):
            self.assertEqual(self._spawn_tick(g, {}, cap=3), ["T-1"])
        self.assertNotIn("waiting", a)

    def test_node_provider_uses_spawn_resolution(self):
        from fleet_rt import config as rt_config
        cfg = rt_config.Config(rt_config._copy(rt_config.DEFAULTS))
        self.assertEqual(fleet_graph._node_provider(cfg, {"slot": "S1"}), "kisti")          # codex 기본 모델
        self.assertEqual(fleet_graph._node_provider(cfg, {"slot": "S1", "harness": "claude"}), "anthropic")
        self.assertEqual(fleet_graph._node_provider(cfg, {"slot": "S1", "model": "openrouter/x"}), "openrouter")
        with mock.patch.object(fleet, "_slot_model", return_value="exaone/k-exaone_v2.5"):
            self.assertEqual(fleet_graph._node_provider(cfg, {"slot": "S2", "harness": "opencode"}), "exaone")
        self.assertIsNone(fleet_graph._node_provider(cfg, {"slot": "S9"}))                  # 명부 밖
        self.assertIsNone(fleet_graph._node_provider(None, {"slot": "S1"}))

    # ---- 5.7 싼 틱
    def test_live_scan_skips_finished_records(self):
        for i in range(5):
            (self.runs / f"OLD-{i}.json").write_text(json.dumps({"slot": "S1", "pid": 999999}), encoding="utf-8")
            (self.runs / f"OLD-{i}.{'rc' if i % 2 else 'lost'}").write_text("0", encoding="utf-8")
        (self.runs / "LIVE.json").write_text(json.dumps({"slot": "S2", "pid": os.getpid()}), encoding="utf-8")
        sroot = self.tmp / "sessions"
        for i in range(5):
            d = sroot / f"S-{i}"
            d.mkdir(parents=True)
            (d / "meta.json").write_text(json.dumps({"id": d.name, "slot": "S1", "provider": "kisti"}), encoding="utf-8")
            (d / "end.json").write_text(json.dumps({"state": "done", "rc": 0}), encoding="utf-8")
        seen = []
        real = fleet._run_state

        def spy(rid):
            seen.append(rid)
            return real(rid)
        from fleet_rt import sessions as rt_sessions
        looked = []
        real_state = rt_sessions.state
        with mock.patch.object(fleet, "_run_state", side_effect=spy), \
             mock.patch.object(rt_sessions, "state", side_effect=lambda d, live=None: looked.append(d) or real_state(d, live)):
            busy, by_prov = fleet_graph._live_scan(self.graph([]))
        self.assertEqual(seen, ["LIVE"])
        self.assertEqual(looked, [])                     # 끝난 세션은 다시 보지 않는다
        self.assertEqual((busy, by_prov), ({"S2"}, {}))

    def test_poll_default_is_two_seconds(self):
        self.assertEqual(fleet_graph.DEFAULT_POLL_SEC, 2.0)
        src = (ROOT / "tools" / "fleet_ctl.py").read_text(encoding="utf-8")
        self.assertIn('"--poll", "2"]', src)
        self.assertNotIn('"--poll", "15"', src)

    # ---- 5.8 보드 동기화
    def _db(self, rows):
        import sqlite3
        import aimem_db
        db = self.tmp / "aimem.db"
        con = sqlite3.connect(db)
        con.executescript(aimem_db.SCHEMA)
        con.execute("INSERT INTO meta(key,value) VALUES('rev','3')")
        con.executemany("INSERT INTO tasks(id,status) VALUES(?,?)", rows)
        con.commit()
        con.close()
        return db

    def _board(self, db):
        import sqlite3
        con = sqlite3.connect(db)
        try:
            return dict(con.execute("SELECT id,status FROM tasks")), con.execute("SELECT count(*) FROM events").fetchone()[0]
        finally:
            con.close()

    def test_board_sync_rules(self):
        db = self._db([("T-1", "TODO"), ("T-2", "DONE"), ("T-3", "REJECTED"), ("T-4", "REVIEW")])
        self.assertIs(fleet_graph._board_sync("T-1", "IN-PROGRESS"), True)
        self.assertIs(fleet_graph._board_sync("T-1", "IN-PROGRESS"), False)        # 같은 값은 다시 안 적는다
        self.assertIs(fleet_graph._board_sync("T-2", "BLOCKED"), False)
        self.assertIs(fleet_graph._board_sync("T-3", "REVIEW"), False)
        self.assertIs(fleet_graph._board_sync("T-404", "REVIEW"), False)            # 행을 만들지 않는다
        self.assertIs(fleet_graph._board_sync("T-4", "BLOCKED"), True)
        board, events = self._board(db)
        self.assertEqual(board, {"T-1": "IN-PROGRESS", "T-2": "DONE", "T-3": "REJECTED", "T-4": "BLOCKED"})
        self.assertEqual(events, 2)

    def test_board_sync_without_db_is_a_no_op(self):
        self.assertIsNone(fleet_graph._board_sync("T-1", "REVIEW"))
        self.assertFalse((self.tmp / "aimem.db").exists())

    def test_step_mirrors_status_changes_and_leaves_todo_alone(self):
        db = self._db([("T-1", "IN-PROGRESS"), ("T-2", "IN-PROGRESS")])
        n1, n2 = self.node("T-1", run="R-1"), self.node("T-2", run="R-2", max_attempts=2)
        g = self.graph([n1, n2])
        states = {"R-1": ("done", 0), "R-2": ("done", 3)}
        with mock.patch.object(fleet, "_run_state", side_effect=lambda r: states[r]), \
             mock.patch.object(fleet, "run_report", return_value="DONE"), \
             mock.patch.object(fleet_graph, "_session_end", return_value=None):
            fleet_graph.step(g, allow_spawn=False)
        self.assertEqual((n1["status"], n2["status"]), ("done", "todo"))
        board, _ = self._board(db)
        self.assertEqual(board, {"T-1": "REVIEW", "T-2": "IN-PROGRESS"})            # 재시도 대기는 그대로

    def test_board_sync_failure_never_breaks_step(self):
        (self.tmp / "aimem.db").write_bytes(b"garbage")
        n = self.node()
        with mock.patch.object(fleet, "_run_state", return_value=("done", 0)), \
             mock.patch.object(fleet, "run_report", return_value="DONE"), \
             mock.patch.object(fleet_graph, "_session_end", return_value=None):
            fleet_graph.step(self.graph([n]), allow_spawn=False)
            n2 = self.node("T-2")
            fleet_graph.step(self.graph([n2]), allow_spawn=False)
        self.assertEqual((n["status"], n2["status"]), ("done", "done"))
        log = (self.graphs / "G-900.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("보드 동기화 실패"), 1)


class ReportEndedInToolCall(unittest.TestCase):
    """R9 T-116: kistillm 이 도구 호출을 글자로 내고 54초 만에 rc 0 으로 끝났는데 느슨한 verify 가 done 을 줬다."""

    def test_detects_only_a_trailing_textual_tool_call(self):
        aborted = ("확인 통과했습니다. 이제 읽겠습니다.\n\n<tool_call>\n<function=update_plan>\n<parameter=plan>\n[]\n"
                   "</parameter>\n</function>\n</tool_call>\n\n")
        self.assertTrue(fleet_graph.report_ended_in_tool_call(aborted))
        self.assertTrue(fleet_graph.report_ended_in_tool_call("읽겠습니다\n<function=shell>"))
        for fine in ("", None, "DONE\n- 다 했다", "본문에 `<tool_call>` 이라는 낱말을 인용\nDONE",
                     "<tool_call>\n</tool_call>\nDONE - 그 뒤에 진짜 보고가 있다"):
            self.assertFalse(fleet_graph.report_ended_in_tool_call(fine), fine)



class WroteNothing(unittest.TestCase):
    """R9 T-117·T-118: 준비만 하다 rc 0 으로 끝난 시도가, 이미 있던 스크립트로 verify 를 통과해 done 이 됐다."""

    def test_first_attempt_that_touched_no_write_path_is_a_noop(self):
        import datetime, os, tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as t:
            root = pathlib.Path(t)
            (root / "p" / "shots").mkdir(parents=True)
            f = root / "p" / "a.py"
            f.write_text("old", encoding="utf-8")
            old = datetime.datetime.now().timestamp() - 3600
            os.utime(f, (old, old))
            att = {"started": datetime.datetime.now().isoformat(timespec="seconds"), "run_id": "x"}
            node = {"id": "T-1", "write": ["p/a.py", "p/shots/**"], "attempts": [att]}
            with mock.patch.object(fleet_graph, "ROOT", root):
                self.assertTrue(fleet_graph.wrote_nothing(node, att))
                (root / "p" / "shots" / "s.png").write_text("x", encoding="utf-8")     # 글롭 경로에 새 파일
                self.assertFalse(fleet_graph.wrote_nothing(node, att))
                (root / "p" / "shots" / "s.png").unlink()
                f.write_text("new", encoding="utf-8")                                    # 정확한 경로를 고침
                self.assertFalse(fleet_graph.wrote_nothing(node, att))
                os.utime(f, (old, old))
                self.assertFalse(fleet_graph.wrote_nothing({**node, "attempts": [att, att]}, att))   # 재시도는 안 본다
                self.assertFalse(fleet_graph.wrote_nothing({**node, "write": []}, att))              # 쓸 것이 없는 노드
                self.assertFalse(fleet_graph.wrote_nothing(node, {"run_id": "x"}))                   # 시작 시각을 모르면 막지 않는다
                self.assertFalse(fleet_graph.wrote_nothing(node, {"started": "어제"}))



class RetryBriefCarriesThePriorReport(unittest.TestCase):
    """재시도 브리프에 검증 출력 꼬리만 가면 두 번째 작업자가 첫 작업자의 결론을 모른 채 다시 조사한다 (R7 T-099)."""

    def _spawn(self, last):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            graphs = pathlib.Path(t)
            g = {"id": "G-900", "nodes": []}
            n = {"id": "T-900", "slot": "S2", "title": "t", "task": "원래 지시", "max_attempts": 2, "attempts": [last]}

            def fake_spawn(ns):
                print("T-900-S2-a2-000000")

            with mock.patch.object(fleet_graph, "GRAPHS", graphs), mock.patch.object(fleet, "cmd_spawn", fake_spawn), \
                 mock.patch.object(fleet_graph, "_log"):
                fleet_graph._spawn_node(g, n, 2)
            return (graphs / "G-900-T-900-a2.task.md").read_text(encoding="utf-8")

    def test_prior_report_is_included_as_a_hint_not_as_truth(self):
        text = self._spawn({"run_id": "T-900-S2-a1-1", "rc": 0, "verify_rc": 1, "verify_tail": "FAIL 3행",
                            "report": "PARTIAL\n- 표 3행의 기대값이 구현과 다르다"})
        self.assertTrue(text.startswith("원래 지시"))
        self.assertIn("FAIL 3행", text)
        self.assertIn("표 3행의 기대값이 구현과 다르다", text)
        self.assertIn("틀렸을 수 있으니", text)

    def test_a_textual_tool_call_is_not_passed_on(self):
        text = self._spawn({"run_id": "T-900-S2-a1-1", "rc": 0, "verify_rc": -2, "verify_tail": "한 일이 없다",
                            "report": "읽겠습니다\n<tool_call>\n<function=update_plan>\n</function>\n</tool_call>"})
        self.assertNotIn("<tool_call>", text)
        self.assertNotIn("직전 작업자의 보고", text)
        self.assertNotIn("직전 작업자의 보고", self._spawn({"run_id": "x", "rc": 1, "verify_rc": -1}))



class RoundBudget(unittest.TestCase):
    """R9 는 상한(그래프 3·태스크 10)을 5·11 로 넘겼고 R10 은 상한 때문에 수정 뒤 재검수를 포기했다."""

    def setUp(self):
        import tempfile
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.g = pathlib.Path(tmp.name)
        p = mock.patch.object(fleet_graph, "GRAPHS", self.g)
        p.start()
        self.addCleanup(p.stop)

    def put(self, gid, rnd, ids):
        (self.g / f"{gid}.json").write_text(json.dumps({"id": gid, "round": rnd, "nodes": [{"id": i} for i in ids]}), encoding="utf-8")

    def test_new_work_stops_at_the_cap_and_review_followups_may_go_on(self):
        chk = fleet_graph.round_budget_problem
        self.assertIsNone(chk(None, ["T-1"], ""))                               # 도는 라운드가 없으면 보지 않는다
        self.put("G-001", 9, ["T-1", "T-2", "T-3", "T-4"])
        self.put("G-002", 9, ["T-5", "T-6", "T-2"])                              # T-2 를 다시 굴려도 한 번만 센다
        self.put("G-003", 8, ["T-90", "T-91"])                                   # 다른 라운드는 세지 않는다
        (self.g / "G-004.json").write_text("{깨진", encoding="utf-8")
        self.assertEqual(fleet_graph.round_usage(9)[0], 2)
        self.assertEqual(len(fleet_graph.round_usage(9)[1]), 6)
        self.assertIsNone(chk(9, ["T-7", "T-8", "T-9", "T-10"], ""))             # 그래프 3 · 태스크 10 - 딱 상한
        self.assertIn("상한", chk(9, ["T-7", "T-8", "T-9", "T-10", "T-11"], ""))  # 태스크 11
        self.put("G-005", 9, ["T-7"])
        msg = chk(9, ["T-8"], "")                                                # 네 번째 그래프
        self.assertIn("--followup", msg)
        self.assertIsNone(chk(9, ["T-8"], "T-100 검수 결함 1~3 수정"))            # 후속이면 된다
        self.assertIsNone(chk(9, ["T-2", "T-5"], "재검수"))                       # 같은 태스크 재실행은 수를 안 늘린다
        self.put("G-006", 9, ["T-8"]); self.put("G-007", 9, ["T-9"]); self.put("G-008", 9, ["T-10"])
        self.assertIn("절대 상한", chk(9, ["T-11"], "재검수"))                     # 일곱 번째 그래프는 후속이어도 안 된다
        self.assertIsNone(chk(9, ["T-11"], "재검수", exclude="G-008"))            # 같은 id 로 다시 만드는 것은 자기 자신을 빼고 센다


if __name__ == "__main__":
    unittest.main()
