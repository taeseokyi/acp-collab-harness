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


if __name__ == "__main__":
    unittest.main()
