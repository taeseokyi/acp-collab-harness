"""운영 방식 키가 /api/fleet/round · chain 으로 엔진에 그대로 넘어가는지 (가짜 fleet_ctl)."""
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
    POLICY_CHOICES = CHOICES
    @staticmethod
    def launch_round(by, policy=None): NewCtl.calls.append(("round", by, policy)); return {"ok": True}
    @staticmethod
    def switch_policy(policy, by, expect_round=None): NewCtl.calls.append(("switch", by, policy, expect_round)); return {"ok": policy != "cost", "error": "거절"}
    @staticmethod
    def chain_policy(policy, by): NewCtl.calls.append(("next", by, policy)); return {"ok": True}
    @staticmethod
    def chain_set(on, target, mx, by, projects=(), fleet_on=False, all_=False, autonomous=False, renew=False, policy=None):
        NewCtl.calls.append(("chain", on, policy)); return {"ok": True}


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

    def test_switch_needs_a_known_policy_and_when_and_passes_refusals_as_409(self):
        code, _ = self.go(NewCtl, "switch", {"policy": "speed", "when": "now", "round": 27})
        self.assertEqual((code, NewCtl.calls), (200, [("switch", "웹", "speed", 27)]))
        code, _ = self.go(NewCtl, "switch", {"policy": "speed", "when": "next"})
        self.assertEqual((code, NewCtl.calls), (200, [("next", "웹", "speed")]))
        for bad in ({}, {"policy": None, "when": "now"}, {"policy": "fast", "when": "now"}, {"policy": 3, "when": "next"}, None, [],
                    {"policy": "speed"}, {"policy": "speed", "when": "later"}, {"policy": "speed", "when": True},
                    {"policy": "speed", "when": "now"}, {"policy": "speed", "when": "now", "round": "27"}, {"policy": "speed", "when": "now", "round": True}):
            code, out = self.go(NewCtl, "switch", bad)
            self.assertEqual((code, NewCtl.calls), (400, []), bad)       # `when` 이 빠지면 멈추지 않는다
        code, out = self.go(NewCtl, "switch", {"policy": "cost", "when": "now", "round": 27})      # 엔진이 거절하면 409
        self.assertEqual((code, out["error"]), (409, "거절"))


class TellPassThrough(unittest.TestCase):
    """`POST /api/fleet/tell` - 말은 엔진(`fleet_ctl.tell`)에 그대로 넘기고, 판정도 엔진이 한다."""

    def go(self, payload, out):
        calls = []

        class Ctl:
            @staticmethod
            def tell(message, by): calls.append((message, by)); return out

        tmp = pathlib.Path(tempfile.gettempdir())
        with mock.patch.object(server, "_fleet_ctl", return_value=Ctl), mock.patch.object(server, "ROOT", tmp.resolve()):
            return server.fleet_action("tell", "웹(태석)", tmp, payload), calls

    def test_message_forwarded_with_who(self):
        (code, out), calls = self.go({"message": "요청을 고쳤습니다"}, {"ok": True, "round": 33})
        self.assertEqual((code, out["round"]), (200, 33))
        self.assertEqual(calls, [("요청을 고쳤습니다", "웹(태석)")])

    def test_engine_refusal_is_409(self):
        (code, out), _ = self.go({"message": "x"}, {"ok": False, "error": "돌고 있는 라운드가 없습니다"})
        self.assertEqual(code, 409)
        self.assertFalse(out["ok"])

    def test_non_string_message_400_without_calling_engine(self):
        for bad in (None, {}, {"message": 3}, {"message": ["x"]}):
            (code, _), calls = self.go(bad, {"ok": True})
            self.assertEqual(code, 400)
            self.assertEqual(calls, [])

    def test_route_is_known(self):
        self.assertTrue(server._REQ_FLEET_RE.match("/api/fleet/tell"))


if __name__ == "__main__":
    unittest.main()
