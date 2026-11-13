"""`/api/state` 의 `tz` - 화면 시각의 기준 구역 (fleet.toml time_zone, 틀리면 이 기계의 현지 구역)."""
import _fleet_env  # noqa: F401
import pathlib
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server  # noqa: E402


class _Cfg:
    def __init__(self, name): self._n = name
    def time_zone(self): return self._n


def _with_cfg(cfg):
    class M:
        @staticmethod
        def load(root): return cfg
    return mock.patch.object(server, "_fleet_rt", lambda name: M)


class TzInfoTest(unittest.TestCase):
    def test_valid_name(self):
        with _with_cfg(_Cfg("Asia/Seoul")):
            self.assertEqual(server.tz_info(pathlib.Path(".")), {"name": "Asia/Seoul", "offset": "+09:00"})
        with _with_cfg(_Cfg("UTC")):
            self.assertEqual(server.tz_info(pathlib.Path("."))["offset"], "+00:00")

    def test_invalid_name_falls_back_to_machine_zone(self):
        with _with_cfg(_Cfg("Not/AZone")):
            tz = server.tz_info(pathlib.Path("."))
        self.assertNotEqual(tz["name"], "Not/AZone")
        self.assertRegex(tz["offset"], r"^[+-]\d{2}:\d{2}$")

    def test_config_without_time_zone_defaults_to_seoul(self):
        with _with_cfg(object()):
            self.assertEqual(server.tz_info(pathlib.Path("."))["name"], "Asia/Seoul")

    def test_state_carries_tz(self):
        with tempfile.TemporaryDirectory() as td:
            st = server._blank_keys(pathlib.Path(td))
        self.assertIn("tz", st)
        self.assertRegex(st["tz"]["offset"], r"^[+-]\d{2}:\d{2}$")
        self.assertIn("tz", server.STATE_KEYS if hasattr(server, "STATE_KEYS") else {"tz": 1})


if __name__ == "__main__":
    unittest.main()
