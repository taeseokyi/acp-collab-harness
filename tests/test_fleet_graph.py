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
        ):
            patcher = mock.patch.object(fleet, attr, return_value=value)
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

    def test_validate_graph_default_still_checks_done_node_slot(self):
        node = self._node("T-1", status="done")
        node["slot"] = "S9"
        graph = self._graph([node])
        problems = fleet_graph.validate_graph(graph)
        self.assertTrue(any("S9" in problem and "명부" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
