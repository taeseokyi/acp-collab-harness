"""슬롯을 도중에 빼고 더하기 (2026-11-14, 태석님 지시).

멈추기(일시 사용 중지)·지우기·더하기는 사람이 하고, 그 뒤의 역할·분담은 관리자가 한다. 엔진이 지키는 것:
  - 멈춘 슬롯으로는 작업자를 띄우지 않는다 (`fleet.spawn`·그래프 실행기·`new`·`move`)
  - 라운드 도중에 멈추거나 지우면 그 슬롯의 작업자를 끊고, 노드는 재시도로 세지 않고 대기(`paused:<S>`·`removed:<S>`)로 둔다
  - 도는 라운드의 관리자에게 알린다 (INBOX) - 관리자가 `move` 로 다시 나눈다
  - 다시 쓰면 기다리던 노드가 뜬다
진짜 하네스는 띄우지 않는다(`_fleet_env`). 상태는 `test_rt_autonomy.Base` 의 임시 저장소.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fleet_env  # noqa: F401,E402

import argparse
import unittest

import aimem_db  # noqa: E402
import fleet  # noqa: E402
import fleet_ctl  # noqa: E402
import fleet_graph  # noqa: E402
import test_rt_autonomy as A  # noqa: E402
from fleet_rt import sessions  # noqa: E402

_SAVED = []


def setUpModule():
    _SAVED.append(A.BASE)
    A.setUpModule()


def tearDownModule():
    try:
        A.tearDownModule()
    finally:
        A.BASE = _SAVED.pop()


RUN = dict(timeout=60, poll=0.1, concurrency=None, stop_on_block=None)


class SlotBase(A.Base):
    SLOTS = (("S1", "claude", "sonnet"), ("S2", "codex", "one/x"), ("S3", "opencode", "wide/y"))

    def setUp(self):
        super().setUp()
        fleet_ctl.set_mode("running", "test")
        self.own("out/T-1.txt", "S2")
        self.own("out/T-2.txt", "S3")

    def running_graph(self):
        """T-1 은 S2 에서 오래, T-2 는 S3 에서 금방."""
        g = self.new_graph([self.node("T-1", "S2", task=A.WORK.format(s=40, w="out/T-1.txt")),
                            self.node("T-2", "S3", task=A.WORK.format(s=0, w="out/T-2.txt"))])
        fleet_graph.step(g)
        self.assertEqual([n["status"] for n in g["nodes"]], ["running", "running"])
        fleet_graph._save(g)
        return g

    def run_graph(self, gid="G-001"):
        return A.quiet(fleet_graph.cmd_run, argparse.Namespace(id=gid, **RUN))

    def inbox(self, n):
        p = self.root / "rounds" / f"R{n}" / "INBOX.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""


class PauseBeforeRound(SlotBase):
    def test_pause_marks_the_roster_and_engine_refuses_the_slot(self):
        out = fleet_ctl.slot_pause("S2", "kisti  장애", "test")
        self.assertEqual((out["ok"], out["changed"], out["cancelled"], out["round"]), (True, True, [], None))
        row = next(r for r in aimem_db.slot_list() if r["slot"] == "S2")
        self.assertTrue(row["paused"])
        self.assertEqual(row["paused_note"], "kisti 장애")
        self.assertIn("slot pause S2 (일시 사용 중지) - kisti 장애", self.events("slot"))
        self.assertEqual(fleet.paused_slots(), {"S2": "kisti 장애"})
        self.assertFalse(fleet_ctl.slot_pause("S2", "", "test")["changed"])          # 두 번 걸어도 같다
        # 브리프의 슬롯 목록이 다음 관리자에게 알린다
        line = next(x for x in fleet_ctl.slot_roster_lines().splitlines() if x.startswith("- S2"))
        self.assertIn("일시 사용 중지 - 쓰지 않음", line)
        self.assertIn("kisti 장애", line)
        # 띄우기·새 그래프·옮기기 모두 거절
        with self.assertRaises(SystemExit) as cm:
            fleet.spawn("S2", "일", write=["out/T-1.txt"])
        self.assertIn("일시 사용 중지된 슬롯", str(cm.exception))
        g = {"id": "G-009", "nodes": [self.node("T-1", "S2")]}
        self.assertIn("T-1: 슬롯 S2 은 일시 사용 중지 중 - 다른 슬롯에 배정하십시오", fleet_graph.validate_graph(g))
        self.assertEqual(fleet_graph.validate_graph(g, spawnable_only=True), [])     # 도는 그래프는 막지 않는다 (기다릴 뿐)
        g = self.new_graph([self.node("T-2", "S3", task="FAKE: report BLOCKED\\n막힘")])
        self.assertTrue(self.drive(g, lambda g: g["nodes"][0]["status"] == "blocked"))
        ok, msg = fleet_graph.move_node(g, "T-2", "S2")
        self.assertFalse(ok)
        self.assertIn("S2 은(는) 일시 사용 중지 중", msg)

    def test_paused_slot_does_not_block_prepare_or_hold_a_provider_seat(self):
        fleet_ctl.slot_pause("S2", "", "test")
        names = [c["name"] for c in fleet_ctl._runtime_checks()]
        self.assertFalse([n for n in names if "S2" in n], names)
        self.assertTrue([n for n in names if "S3" in n], names)
        # 공급자 one 은 동시 1 - 멈춘 S2 가 자리를 잡고 있지 않으니 관리자가 같은 공급자의 슬롯을 하나 둘 수 있다
        self.round_json(5, policy="cost")
        with self.manager_env("M-R5-000000"):
            self.assertEqual(aimem_db.slot_add(None, "codex", "one/x")["slot"], "S4")

    def test_only_the_owner_pauses_and_resumes(self):
        with self.manager_env("M-R5-000000"):
            out = fleet_ctl.slot_pause("S2", "", "관리자")
            self.assertFalse(out["ok"])
            self.assertIn("사람이 합니다", out["error"])
        fleet_ctl.slot_pause("S2", "", "test")
        with self.manager_env("M-R5-000000"):
            self.assertFalse(fleet_ctl.slot_resume("S2", "관리자")["ok"])
        self.assertFalse(fleet_ctl.slot_pause("S9", "", "test")["ok"])
        self.assertEqual(fleet.paused_slots(), {"S2": ""})

    def test_resume_lets_the_waiting_node_run(self):
        g = self.new_graph([self.node("T-1", "S2", task=A.WORK.format(s=0, w="out/T-1.txt"))])
        fleet_ctl.slot_pause("S2", "", "test")
        fleet_graph.step(g)
        n = g["nodes"][0]
        self.assertEqual((n["status"], n["waiting"], n.get("attempts", [])), ("todo", "paused:S2", []))
        fleet_graph._save(g)
        rc, text, err = self.run_graph()                                  # 기다려도 풀리지 않으니 곧 돌아온다
        self.assertEqual(rc, 1, text + err)
        self.assertIn("쓸 수 없는 슬롯에 걸린 노드: T-1(S2 일시 사용 중지)", text)
        out = fleet_ctl.slot_resume("S2", "test")
        self.assertEqual((out["ok"], out["changed"]), (True, True))
        self.assertIn("slot resume S2", " ".join(self.events("slot")))
        rc, text, err = self.run_graph()
        self.assertEqual(rc, 0, text + err)
        self.assertNotIn("waiting", fleet_graph._load("G-001")["nodes"][0])


class PauseMidRound(SlotBase):
    def test_pause_cancels_the_worker_and_the_manager_reassigns(self):
        mgr = self.launch_manager("speed")
        rnd = mgr["round"]
        g = self.running_graph()
        run_id = g["nodes"][0]["attempts"][0]["run_id"]
        out = fleet_ctl.slot_pause("S2", "응답 없음", "태석")
        self.assertEqual((out["cancelled"], out["round"], out["refused"]), ([run_id], rnd, []))
        self.assertEqual([(x["graph"], x["node"]) for x in out["nodes"]], [("G-001", "T-1")])
        self.assertNotEqual(sessions.state(self.sroot / run_id)["state"], "running")
        box = self.inbox(rnd)
        for want in ("슬롯 S2 을(를) 일시 사용 중지했습니다 (까닭: 응답 없음)", f"끊은 작업자: {run_id}", "G-001 T-1(running)",
                     "fleet_graph.py move", "재시도 횟수로 세지 않습니다", "지금 슬롯:", "- S3 "):
            self.assertIn(want, box)
        # 실행기: 끊긴 시도는 세지 않고 노드는 대기, 다른 슬롯의 노드는 끝까지 간다. 걸린 채 돌아온다
        rc, text, err = self.run_graph()
        self.assertEqual(rc, 1, text + err)
        self.assertIn("쓸 수 없는 슬롯에 걸린 노드: T-1(S2 일시 사용 중지)", text)
        g = fleet_graph._load("G-001")
        n1, n2 = g["nodes"]
        self.assertEqual((n1["status"], n1["waiting"], n1["attempts"], n2["status"]), ("todo", "paused:S2", [], "done"))
        self.assertEqual([a["stopped_by"] for a in n1["stopped_attempts"]], ["슬롯 S2 일시 사용 중지"])
        # 관리자가 다른 슬롯으로 옮기면 처음 시도로 뜬다
        n1["task"] = A.WORK.format(s=0, w="out/T-1.txt")
        fleet_graph._save(g)
        with self.manager_env(mgr["session"]):
            rc, text, err = A.quiet(fleet_graph.cmd_move, argparse.Namespace(id="G-001", node="T-1", slot="S3", why="S2 멈춤"))
        self.assertEqual(rc, 0, err)
        rc, text, err = self.run_graph()
        self.assertEqual(rc, 0, text + err)
        g = fleet_graph._load("G-001")
        self.assertEqual((g["nodes"][0]["slot"], len(g["nodes"][0]["attempts"]), self.owner_of("out/T-1.txt")), ("S3", 1, "S3"))
        # 다시 쓰는 것도 관리자에게 알린다
        self.assertEqual(fleet_ctl.slot_resume("S2", "태석")["round"], rnd)
        self.assertIn("슬롯 S2 을(를) 다시 씁니다", self.inbox(rnd))
        fleet_ctl.stop("test")

    def test_runner_cuts_a_worker_the_pause_did_not(self):
        """DB 만 바뀐 경우(끊기 전에 죽은 호출 등)에도 실행기가 끊는다."""
        g = self.running_graph()
        run_id = g["nodes"][0]["attempts"][0]["run_id"]
        aimem_db.slot_pause("S2", "", "test")
        fleet_graph.step(g)
        n1 = g["nodes"][0]
        self.assertEqual((n1["status"], n1["waiting"], n1["attempts"]), ("todo", "paused:S2", []))
        self.assertEqual(n1["stopped_attempts"][0]["kill_outcome"], "killed")
        self.assertTrue(A._wait(lambda: sessions.state(self.sroot / run_id)["state"] != "running", 5))

    def test_a_run_that_finished_before_the_pause_is_reaped(self):
        g = self.new_graph([self.node("T-1", "S2", task=A.WORK.format(s=0, w="out/T-1.txt"))])
        fleet_graph.step(g)
        run_id = g["nodes"][0]["attempts"][0]["run_id"]
        self.assertTrue(A._wait(lambda: sessions.state(self.sroot / run_id)["state"] == "done", 10))
        fleet_ctl.slot_pause("S2", "", "test")
        fleet_graph.step(g)
        self.assertEqual(g["nodes"][0]["status"], "done")


class RemoveMidRound(SlotBase):
    def test_remove_cancels_the_worker_and_the_manager_reassigns(self):
        mgr = self.launch_manager("speed")
        rnd = mgr["round"]
        g = self.running_graph()
        run_id = g["nodes"][0]["attempts"][0]["run_id"]
        with aimem_db.connect() as con:
            con.execute("INSERT INTO tasks(id,title,slot,status) VALUES('T-1','일','S2','IN-PROGRESS')")
            con.commit()
        out = fleet_ctl.slot_remove("S2", "태석")
        self.assertFalse(out["ok"])                                       # 배정된 일이 있으면 force 없이는 끊지도 지우지도 않는다
        self.assertIn("끝나지 않은 태스크가 있습니다: T-1", out["error"])
        self.assertIn(f"도는 작업자 {run_id} 를 끊습니다", out["error"])
        self.assertEqual(sessions.state(self.sroot / run_id)["state"], "running")
        out = fleet_ctl.slot_remove("S2", "태석", force=True)
        self.assertEqual((out["ok"], out["cancelled"], out["round"]), (True, [run_id], rnd))
        self.assertEqual([s["slot"] for s in aimem_db.slot_list()], ["S1", "S3"])
        box = self.inbox(rnd)
        for want in ("슬롯 S2 을(를) 명부에서 지웠습니다", f"끊은 작업자: {run_id}", "G-001 T-1(running)", "fleet_graph.py move"):
            self.assertIn(want, box)
        rc, text, err = self.run_graph()
        self.assertEqual(rc, 1, text + err)
        self.assertIn("쓸 수 없는 슬롯에 걸린 노드: T-1(S2 명부에서 삭제됨)", text)
        g = fleet_graph._load("G-001")
        n1 = g["nodes"][0]
        self.assertEqual((n1["status"], n1["waiting"], n1["attempts"]), ("todo", "removed:S2", []))
        n1["task"] = A.WORK.format(s=0, w="out/T-1.txt")
        fleet_graph._save(g)
        ok, msg = fleet_graph.move_node(g, "T-1", "S3", policy="speed")
        self.assertTrue(ok, msg)
        fleet_graph._save(g)
        rc, text, err = self.run_graph()
        self.assertEqual(rc, 0, text + err)
        self.assertEqual(self.owner_of("out/T-1.txt"), "S3")
        fleet_ctl.stop("test")

    def test_manager_still_cannot_remove_a_busy_or_owner_slot(self):
        g = self.running_graph()
        with self.manager_env("M-R5-000000"):
            out = fleet_ctl.slot_remove("S2", "관리자")
        self.assertFalse(out["ok"])
        self.assertIn("사람이 둔 슬롯이라 관리자는 지우지 않습니다", out["error"])
        self.assertEqual(sessions.state(self.sroot / g["nodes"][0]["attempts"][0]["run_id"])["state"], "running")
        self.assertFalse(fleet_ctl.slot_remove("S9", "test")["ok"])


class AddMidRound(SlotBase):
    def test_adding_a_slot_tells_the_running_manager(self):
        self.assertIsNone(fleet_ctl.slot_changed("add", {"slot": "S4", "harness": "opencode", "model": "wide/y"}, "태석"))   # 라운드 밖: 브리프·요청이 알린다
        mgr = self.launch_manager("cost")
        row = aimem_db.slot_add(None, "opencode", "wide/y", aimem_db.SLOT_ROLE_UNASSIGNED, "", "태석")
        self.assertEqual(fleet_ctl.slot_changed("add", row, "태석"), mgr["round"])
        box = self.inbox(mgr["round"])
        for want in ("슬롯 S4 이(가) 추가됐습니다 (opencode, 모델 wide/y)", "slot set --slot S4 --role", "- S4 "):
            self.assertIn(want, box)
        # 관리자는 사람이 더한 슬롯의 역할을 정하고 일을 맡긴다
        with self.manager_env(mgr["session"]):
            _r, ch = aimem_db.slot_set("S4", role="만들기")
        self.assertEqual(ch, ["역할"])
        fleet_ctl.stop("test")


if __name__ == "__main__":
    unittest.main()
