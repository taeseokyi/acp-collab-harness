"""운영 방침 키가 /api/fleet/round · chain 으로 엔진에 그대로 넘어가는지 (가짜 fleet_ctl)."""
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server  # noqa: E402

CHOICES = [{"key": k} for k in ("cost", "quality", "speed")]


class NewCtl:
    calls = []
    @staticmethod
    def public_state(): return {"policy": {"choices": CHOICES}}
    @staticmethod
    def launch_round(by, policy=None): NewCtl.calls.append(("round", by, policy)); return {"ok": True}
    @staticmethod
    def chain_set(on, target, mx, by, projects=(), fleet_on=False, all_=False, autonomous=False, renew=False, policy=None):
        NewCtl.calls.append(("chain", on, policy)); return {"ok": True}


class OldCtl:
    calls = []
    @staticmethod
    def public_state(): return {}
    @staticmethod
    def launch_round(by): OldCtl.calls.append(("round", by)); return {"ok": True}
    @staticmethod
    def chain_set(on, target, mx, by, projects=(), fleet_on=False, all_=False, autonomous=False, renew=False):
        OldCtl.calls.append(("chain", on)); return {"ok": True}


class PolicyPassThrough(unittest.TestCase):
    def go(self, ctl, action, payload):
        ctl.calls.clear()
        with mock.patch.object(server, "_fleet_ctl", return_value=ctl), mock.patch.object(server, "ROOT", pathlib.Path(tempfile.gettempdir()).resolve()):
            return server.fleet_action(action, "웹", pathlib.Path(tempfile.gettempdir()), payload)

    def test_round_valid_key_forwarded(self):
        code, _ = self.go(NewCtl, "round", {"policy": "speed"})
        self.assertEqual(code, 200)
        self.assertEqual(NewCtl.calls, [("round", "웹", "speed")])

    def test_round_without_key_keeps_old_shape(self):
        self.go(NewCtl, "round", {})
        self.assertEqual(NewCtl.calls, [("round", "웹", None)])

    def test_invalid_keys_400(self):
        for bad in ("fast", 3, ["cost"], ""):
            code, out = self.go(NewCtl, "round", {"policy": bad})
            self.assertEqual(code, 400, bad)
            self.assertFalse(out["ok"])
            code, _ = self.go(NewCtl, "chain", {"on": True, "fleet": True, "policy": bad})
            self.assertEqual(code, 400, bad)
        self.assertEqual(NewCtl.calls, [])

    def test_chain_forwarded_and_off_ignores(self):
        self.go(NewCtl, "chain", {"on": True, "fleet": True, "policy": "quality"})
        self.assertEqual(NewCtl.calls, [("chain", True, "quality")])
        self.go(NewCtl, "chain", {"on": False, "policy": "bogus"})
        self.assertEqual(NewCtl.calls, [("chain", False, None)])

    def test_old_engine_refuses_a_chosen_policy_instead_of_dropping_it(self):
        """고른 운영 방식을 받지 못하는 옛 엔진이면 말없이 버리고 띄우지 않는다 - 409 와 '모니터를 다시 띄우십시오'."""
        code, out = self.go(OldCtl, "round", {"policy": "speed"})
        self.assertEqual((code, OldCtl.calls), (409, []))
        self.assertIn("모니터를 다시 띄우십시오", out["error"])
        code, out = self.go(OldCtl, "chain", {"on": True, "fleet": True, "policy": "speed"})
        self.assertEqual((code, OldCtl.calls), (409, []))
        self.assertIn("모니터를 다시 띄우십시오", out["error"])
        code, _ = self.go(OldCtl, "round", {})                       # 고르지 않았으면 옛 엔진도 그대로 띄운다
        self.assertEqual((code, OldCtl.calls), (200, [("round", "웹")]))


if __name__ == "__main__":
    unittest.main()
