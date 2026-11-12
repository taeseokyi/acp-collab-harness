import json, pathlib, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server  # noqa: E402


class GraphFieldsTest(unittest.TestCase):
    def collect(self, nodes):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / ".aimem" / "graph").mkdir(parents=True)
        (root / ".aimem" / "graph" / "G-1.json").write_text(json.dumps({"id": "G-1", "nodes": nodes}), encoding="utf-8")
        errs = []
        return server.collect_graphs(root, errs)[0]["nodes"], errs

    def test_new_fields_pass_through(self):
        nodes, errs = self.collect([
            {"id": "N1", "status": "todo", "waiting": "provider:kisti"},
            {"id": "N2", "status": "blocked", "infra": True,
             "infra_attempts": [{"run_id": "r1", "fail_kind": "infra", "why": "침묵"}, {"run_id": "r0", "cleared": True}],
             "attempts": [{"run_id": "r2", "fail_kind": "work", "session_state": "stalled"}]},
        ])
        self.assertEqual(errs, [])
        self.assertEqual(nodes[0]["waiting"], "provider:kisti")
        self.assertFalse(nodes[0]["infra"])
        self.assertEqual(nodes[1]["infra_attempts"], 1)
        self.assertTrue(nodes[1]["infra"])
        self.assertEqual([a["run_id"] for a in nodes[1]["attempt_log"]], ["r0", "r1", "r2"])
        self.assertEqual(nodes[1]["attempt_log"][2]["session_state"], "stalled")

    def test_garbage_is_tolerated(self):
        nodes, errs = self.collect([{"id": "N", "waiting": 5, "infra_attempts": "x", "attempts": ["a", {"why": "w"}]}])
        self.assertEqual(errs, [])
        self.assertIsNone(nodes[0]["waiting"])
        self.assertEqual(nodes[0]["infra_attempts"], 0)
        self.assertEqual(nodes[0]["attempt_log"][0]["why"], "w")


if __name__ == "__main__":
    unittest.main()
