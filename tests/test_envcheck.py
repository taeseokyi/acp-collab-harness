"""envcheck 의 함대 점검 (`sessions` 계층) - 진짜 하네스를 부르지 않는다 (`_fleet_env` 가 fake 로 고정)."""
import _fleet_env  # noqa: F401  - AIFLEET_HARNESS=fake, tools/ 를 sys.path 에
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from envcheck import CHANGED, OK, UNKNOWN, STATUSES
from envcheck import runtime, sessions
from envcheck.__main__ import STRUCTURAL_UNKNOWN, run_layer


class FleetChecks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        p = mock.patch.object(sessions, "ROOT", self.root)
        p.start()
        self.addCleanup(p.stop)

    def _slots(self, rows):
        p = mock.patch.object(sessions, "_slots", return_value=rows)
        p.start()
        self.addCleanup(p.stop)

    def test_result_shape_and_ids(self):
        self._slots([])
        res, err = run_layer("sessions")
        self.assertIsNone(err)
        names = [n for n, _s, _e in res]
        self.assertEqual(names, ["sessions.harness.claude", "sessions.harness.codex", "sessions.harness.opencode",
                                 "sessions.fleet_toml", "sessions.env_file", "sessions.slot_providers"])
        for _n, st, ev in res:
            self.assertIn(st, STATUSES)
            self.assertIsInstance(ev, str)

    def test_harness_probe_is_fake_and_ok(self):
        for n in ("claude", "codex", "opencode"):
            name, st, ev = sessions._check_harness(n)
            self.assertEqual((name, st), (f"harness.{n}", OK))

    def test_missing_binary_changed_only_when_a_slot_uses_it(self):
        from fleet_rt.base import ProbeResult
        fake = mock.Mock()
        fake.get.return_value.probe.return_value = ProbeResult(False, detail="없음")
        with mock.patch.object(sessions, "_rt", return_value=(None, None, fake)):
            self._slots([{"slot": "S2", "harness": "codex", "model": None}])
            self.assertEqual(sessions._check_harness("codex")[1], CHANGED)
            self.assertEqual(sessions._check_harness("opencode")[1], UNKNOWN)

    def test_fleet_toml_defaults_and_broken(self):
        self.assertEqual(sessions._check_fleet_toml()[1], OK)        # 파일 없음 = 내장 기본값
        (self.root / "fleet.toml").write_text("[providers\n", encoding="utf-8")
        self.assertEqual(sessions._check_fleet_toml()[1], CHANGED)

    def test_env_file_needs_mode_600(self):
        self.assertEqual(sessions._check_env_file()[1], CHANGED)     # 없음
        env = self.root / ".env"
        env.write_text("KISTI_API_KEY=x\n", encoding="utf-8")
        os.chmod(env, 0o644)
        self.assertEqual(sessions._check_env_file()[1], CHANGED)
        os.chmod(env, 0o600)
        self.assertEqual(sessions._check_env_file()[1], OK)

    def test_slot_providers(self):
        self._slots([{"slot": "S1", "harness": "claude", "model": "opus"},
                     {"slot": "S2", "harness": "codex", "model": None},
                     {"slot": "S3", "harness": "opencode", "model": "kisti/kistillm"}])
        self.assertEqual(sessions._check_slot_providers()[1], OK)
        self._slots([{"slot": "S1", "harness": "claude", "model": "kisti/kistillm"}])   # claude 는 anthropic 만
        name, st, ev = sessions._check_slot_providers()
        self.assertEqual(st, CHANGED)
        self.assertIn("S1", ev)
        self._slots([{"slot": "S9", "harness": "codex", "model": "nope/none"}])
        self.assertEqual(sessions._check_slot_providers()[1], CHANGED)
        self._slots([])
        self.assertEqual(sessions._check_slot_providers()[1], UNKNOWN)


class NoOpenclawLeft(unittest.TestCase):
    def test_no_external_tool_names_in_checks(self):
        self.assertNotIn("sessions.acp.can_create_sessions", STRUCTURAL_UNKNOWN)
        for mod in (sessions, runtime):
            src = pathlib.Path(mod.__file__).read_text(encoding="utf-8").lower()
            self.assertNotIn("openclaw.json", src)
            self.assertNotIn("acpx", src)

    def test_runtime_layer_items(self):
        with mock.patch.object(runtime, "_check_wsl_dns", return_value=("wsl_dns_first_lookup", UNKNOWN, "x")):
            names = [n for n, _s, _e in runtime.check()]
        self.assertEqual(names, ["python_env", "wsl_dns_first_lookup"])


if __name__ == "__main__":
    unittest.main()
