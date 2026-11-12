"""`/api/state` 가 그래프마다 실행 기록 전체를 다시 읽지 않는다 (2026-11-12 모바일 검수에서 발견).

그래프 41개 × 실행 기록 260건을 그래프마다 다시 읽어 한 번 갱신이 7~11초 걸렸고, 5초마다 부르는 화면이
폰에서 늘 '불러오는 중' 이었다. 하네스별 소요 표본은 한 번 갱신에 한 번만 구한다.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import fleet_graph  # noqa: E402
from aimem_monitor import server  # noqa: E402


class StateSpeedTest(unittest.TestCase):
    def test_durations_are_computed_once_for_all_graphs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            gdir = root / ".aimem" / "graph"
            gdir.mkdir(parents=True)
            for i in range(5):
                (gdir / f"G-{i:03d}.json").write_text(json.dumps(
                    {"id": f"G-{i:03d}", "nodes": [{"id": "T-1", "slot": "S1", "status": "done", "task": "x"}]}),
                    encoding="utf-8")
            calls = []
            with mock.patch.object(server, "ROOT", root), \
                 mock.patch.object(fleet_graph, "harness_durations", side_effect=lambda: calls.append(1) or {}):
                graphs = server.collect_graphs(root, [])
        self.assertEqual(len(graphs), 5)
        self.assertEqual(len(calls), 1)

    def test_progress_uses_given_durations(self):
        g = {"nodes": [{"id": "T-1", "slot": "S1", "status": "done", "task": "x"},
                       {"id": "T-2", "slot": "S1", "status": "todo", "task": "x", "deps": ["T-1"]}]}
        with mock.patch.object(fleet_graph, "harness_durations", side_effect=AssertionError("다시 구하면 안 된다")):
            p = fleet_graph.progress(g, {"claude": [100.0]})
        self.assertEqual(p["percent"], 50.0)


if __name__ == "__main__":
    unittest.main()
