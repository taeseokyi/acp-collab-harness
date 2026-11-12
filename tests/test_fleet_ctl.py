"""`tools/fleet_ctl.py` - 함대 모드(준비/실행/일시 중지/완전 중지)와 그것을 지키는 쪽 (2026-11-10).

실제 `.aimem` 은 건드리지 않습니다 - `fleet.RUNS` 와 `fleet_graph.GRAPHS` 를 임시 디렉터리로
갈아끼우면 모드 파일(`RUNS.parent/fleet-mode.json`)도 따라갑니다. 작업자는 띄우지 않습니다.
"""
import argparse
import contextlib
import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fleet  # noqa: E402
import fleet_ctl  # noqa: E402
import fleet_graph  # noqa: E402


class FleetCtlTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        self.runs = self.tmp / "runs"
        self.graphs = self.tmp / "graph"
        self.runs.mkdir()
        self.graphs.mkdir()
        for module, attr, value in ((fleet, "RUNS", self.runs), (fleet_graph, "GRAPHS", self.graphs),
                                    (fleet_graph, "_LOGGED_ONCE", set())):
            p = mock.patch.object(module, attr, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict("os.environ", {fleet_ctl.FORCE_ENV: ""})
        p.start()
        self.addCleanup(p.stop)

    def _now(self):
        return dt.datetime.now().isoformat(timespec="seconds")

    def graph(self, nodes):
        g = {"id": "G-901", "request": "ctl test", "created": self._now(), "concurrency": 3, "nodes": nodes}
        (self.graphs / "G-901.json").write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
        return g

    def node(self, nid, status="todo", attempts=None):
        return {"id": nid, "title": nid, "slot": "S2", "task": "t", "deps": [], "write": [],
                "max_attempts": 2, "status": status, "attempts": list(attempts or [])}

    # -------------------------------------------------------------- 모드 파일
    def test_missing_file_means_running(self):
        self.assertEqual(fleet_ctl.mode(), "running")
        self.assertTrue(fleet_ctl.spawn_allowed()[0])

    def test_set_mode_round_trip_and_validation(self):
        rec = fleet_ctl.set_mode("paused", "test", "n")
        self.assertEqual((rec["mode"], rec["prev"]), ("paused", "running"))
        self.assertEqual(fleet_ctl.mode(), "paused")
        self.assertTrue((self.tmp / "fleet-mode.json").exists())
        with self.assertRaises(ValueError):
            fleet_ctl.set_mode("bogus")

    def test_corrupt_file_falls_back_to_running(self):
        (self.tmp / "fleet-mode.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(fleet_ctl.mode(), "running")

    def test_spawn_allowed_only_when_running(self):
        for m in ("ready", "paused", "stopped"):
            fleet_ctl.set_mode(m, "test")
            ok, why = fleet_ctl.spawn_allowed()
            self.assertFalse(ok, m)
            self.assertIn(fleet_ctl.MODE_LABEL[m], why)
        fleet_ctl.set_mode("running", "test")
        self.assertTrue(fleet_ctl.spawn_allowed()[0])

    def test_force_env_overrides(self):
        fleet_ctl.set_mode("paused", "test")
        with mock.patch.dict("os.environ", {fleet_ctl.FORCE_ENV: "1"}):
            ok, why = fleet_ctl.spawn_allowed()
        self.assertTrue(ok)
        self.assertIn(fleet_ctl.FORCE_ENV, why)

    # -------------------------------------------------------------- fleet.py spawn
    def test_fleet_spawn_refuses_when_paused(self):
        fleet_ctl.set_mode("paused", "test")
        args = argparse.Namespace(slot="S2", harness=None, write=[], task="x", task_file=None)
        with mock.patch.object(fleet, "roster") as roster:
            with self.assertRaises(SystemExit) as cm:
                fleet.cmd_spawn(args)
        self.assertIn("일시 중지", str(cm.exception.code))
        roster.assert_not_called()   # 명부도 읽기 전에 거절

    # -------------------------------------------------------------- fleet_graph
    def test_step_paused_reaps_but_does_not_spawn(self):
        g = self.graph([self.node("A")])
        fleet_ctl.set_mode("paused", "test")
        with mock.patch.object(fleet_graph, "_spawn_node") as spawn:
            fleet_graph.step(g)
        spawn.assert_not_called()
        self.assertEqual(g["nodes"][0]["status"], "todo")

    def test_step_running_spawns(self):
        g = self.graph([self.node("A")])
        fleet_ctl.set_mode("running", "test")
        with mock.patch.object(fleet_graph, "_spawn_node") as spawn:
            fleet_graph.step(g)
        spawn.assert_called_once()

    def test_step_stopped_halts_running_without_counting_attempt(self):
        att = {"run_id": "T-1-S2-a1-000000", "started": self._now()}
        g = self.graph([self.node("A", "running", [att]), self.node("B")])
        fleet_ctl.set_mode("stopped", "test")
        with mock.patch.object(fleet_graph, "_kill_run", return_value=(123, "killed")) as kill, \
                mock.patch.object(fleet_graph, "_spawn_node") as spawn:
            fleet_graph.step(g)
        kill.assert_called_once_with("T-1-S2-a1-000000", with_outcome=True)
        spawn.assert_not_called()
        a = g["nodes"][0]
        self.assertEqual(a["status"], "todo")
        self.assertEqual(a["attempts"], [])                       # 재시도 횟수로 세지 않음
        self.assertEqual(a["stopped_attempts"][0]["state"], "stopped")
        self.assertTrue((self.runs / "T-1-S2-a1-000000.lost").exists())

    def test_halt_refused_kill_goes_blocked(self):
        att = {"run_id": "T-2-S2-a1-000000", "started": self._now()}
        g = self.graph([self.node("A", "running", [att])])
        fleet_graph._LAST_REFUSAL["T-2-S2-a1-000000"] = "세션 리더 아님"
        with mock.patch.object(fleet_graph, "_kill_run", return_value=(5, "refused")):
            self.assertTrue(fleet_graph.halt_running(g))
        self.assertEqual(g["nodes"][0]["status"], "blocked")
        self.assertFalse((self.runs / "T-2-S2-a1-000000.lost").exists())

    def test_run_loop_exits_3_on_stop(self):
        self.graph([self.node("A")])
        fleet_ctl.set_mode("stopped", "test")
        a = argparse.Namespace(id="G-901", timeout=30, poll=0, concurrency=None)
        with mock.patch.object(fleet_graph, "_validate_or_report", return_value=True), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            rc = fleet_graph.cmd_run(a)
        self.assertEqual(rc, 3)
        self.assertIn("완전 중지", out.getvalue())

    # -------------------------------------------------------------- 브리프 선택
    def test_latest_brief_ignores_drafts_and_used_rounds(self):
        repo = self.tmp / "repo"
        briefs = repo / ".aimem" / "briefs"
        briefs.mkdir(parents=True)
        for name in ("manager-round6-2026-11-10.md", "manager-round7-2026-11-10.md", "manager-round8-draft.md"):
            (briefs / name).write_text("x", encoding="utf-8")
        with mock.patch.object(fleet, "ROOT", repo), \
                mock.patch.object(fleet_ctl, "_used_rounds", return_value={6}):
            b = fleet_ctl.latest_brief()
        self.assertEqual((b["round"], b["file"]), (7, "manager-round7-2026-11-10.md"))
        self.assertIn("manager-round8-draft.md", b["drafts"])
        with mock.patch.object(fleet, "ROOT", repo), \
                mock.patch.object(fleet_ctl, "_used_rounds", return_value={6, 7}):
            self.assertIsNone(fleet_ctl.latest_brief()["file"])   # 이미 띄운 라운드는 다시 쓰지 않는다

    def test_standard_brief_is_used_when_no_round_specific_brief(self):
        # 2026-11-10 태석님 지시: 라운드 내용은 웹 요청으로 정한다 - 그 라운드만의 브리프가 없으면 표준 브리프로 다음 번호.
        repo = self.tmp / "repo"
        briefs = repo / ".aimem" / "briefs"
        briefs.mkdir(parents=True)
        (briefs / "manager-round6-2026-11-10.md").write_text("x", encoding="utf-8")
        with mock.patch.object(fleet, "ROOT", repo), mock.patch.object(fleet_ctl, "_used_rounds", return_value={6}):
            self.assertIsNone(fleet_ctl.latest_brief()["file"])            # 표준 브리프 파일이 없으면 예전 그대로
            (briefs / fleet_ctl.STANDARD_BRIEF).write_text("R{round} / {date} / REV {rev} / {workspace}\n", encoding="utf-8")
            b = fleet_ctl.latest_brief()
            self.assertEqual((b["round"], b["file"], b["standard"]), (7, fleet_ctl.STANDARD_BRIEF, True))
            self.assertEqual(b["drafts"], [])                              # 표준 브리프는 초안으로 세지 않는다
            with mock.patch.object(fleet, "read_rev", return_value=138):
                path = fleet_ctl._round_brief_path(b, dt.datetime(2026, 11, 10, 19, 0))
            self.assertEqual(path, repo / "rounds" / "R7" / "brief.md")     # 라운드 작업 공간에 보낸 그대로 남는다
            self.assertEqual(path.read_text(encoding="utf-8"), "R7 / 2026-11-10 19:00 / REV 138 / rounds/R7\n")
            self.assertEqual(b["workspace"], "rounds/R7")
            (briefs / "manager-round9-2026-11-11.md").write_text("x", encoding="utf-8")
            b = fleet_ctl.latest_brief()                                   # 그 라운드만의 확정본이 있으면 그것이 먼저
            self.assertEqual((b["round"], b["file"], b["standard"]), (9, "manager-round9-2026-11-11.md", False))
            path = fleet_ctl._round_brief_path(b, dt.datetime.now())
            self.assertEqual(path, repo / "rounds" / "R9" / "brief.md")
            self.assertTrue(path.read_text(encoding="utf-8").startswith("x\n"))
            self.assertIn("rounds/R9/", path.read_text(encoding="utf-8"))
        with mock.patch.object(fleet, "ROOT", repo), mock.patch.object(fleet_ctl, "_used_rounds", return_value={6, 9, 12}):
            b = fleet_ctl.latest_brief()                                   # 번호는 쓰인 것 중 가장 큰 것 다음
            self.assertEqual((b["round"], b["standard"]), (13, True))

    def test_rounds_recorded_in_handoff_log_count_as_used(self):
        # 세션도 전달 기록도 없을 때(게이트웨이 정지 등) 이미 돈 라운드의 브리프를 다시 고르면 안 된다.
        import sqlite3
        con = sqlite3.connect(self.tmp / "aimem.db")
        with con:
            con.execute("CREATE TABLE events(at TEXT, actor TEXT, rev INTEGER, kind TEXT, body TEXT)")
            con.executemany("INSERT INTO events VALUES('t',?,1,?,'b')",
                            [("관리자(R6)", "handoff"), ("Manager (R5)", "handoff"), ("Claude Code", "handoff"),
                             ("관리자(R9)", "task")])
        con.close()
        self.assertEqual(fleet_ctl._db_rounds(), {5, 6})
        repo = self.tmp / "repo"
        briefs = repo / ".aimem" / "briefs"
        briefs.mkdir(parents=True)
        (briefs / "manager-round6-2026-11-10.md").write_text("x", encoding="utf-8")
        (briefs / fleet_ctl.STANDARD_BRIEF).write_text("x", encoding="utf-8")
        with mock.patch.object(fleet, "ROOT", repo), mock.patch.object(fleet_ctl, "_manager_sessions", return_value=[]):
            b = fleet_ctl.latest_brief()
            self.assertEqual((b["round"], b["standard"]), (7, True))
            self.assertEqual(fleet_ctl.public_state()["brief"]["round"], 7)

    def test_round_record_lists_open_requests_and_their_projects(self):
        repo = self.tmp / "repo"
        reqs = repo / ".aimem" / "requests"
        reqs.mkdir(parents=True)
        for rid, proj, status in (("Q-1", "알파", "NEW"), ("Q-2", "", "PLANNED"), ("Q-3", "베타", "DONE"), ("Q-4", "알파", "IN-PROGRESS")):
            (reqs / f"{rid}.json").write_text(json.dumps({"id": rid, "project": proj, "status": status}), encoding="utf-8")
        (reqs / "broken.json").write_text("{", encoding="utf-8")
        with mock.patch.object(fleet, "ROOT", repo):
            rec = fleet_ctl._write_round_record(7, dt.datetime(2026, 11, 10, 20, 0), "manager-round-standard.md")
        saved = json.loads((repo / "rounds" / "R7" / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, rec)
        self.assertEqual((saved["round"], saved["at"], saved["projects"], saved["requests"]),
                         (7, "2026-11-10T20:00:00", ["알파"], ["Q-1", "Q-2", "Q-4"]))

    def test_failed_launch_is_marked_in_round_record(self):
        repo = self.tmp / "repo2"
        (repo / ".aimem" / "requests").mkdir(parents=True)
        (repo / ".aimem" / "requests" / "Q-1.json").write_text(json.dumps({"id": "Q-1", "project": "알파", "status": "NEW"}), encoding="utf-8")
        with mock.patch.object(fleet, "ROOT", repo):
            fleet_ctl._write_round_record(7, dt.datetime(2026, 11, 10, 20, 0), "manager-round-standard.md")
            fleet_ctl._mark_round_record_failed(7)
            fleet_ctl._mark_round_record_failed(8)      # 기록이 없어도 조용히
        saved = json.loads((repo / "rounds" / "R7" / "round.json").read_text(encoding="utf-8"))
        self.assertEqual((saved["state"], saved["projects"]), ("failed", ["알파"]))
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
        from aimem_monitor import server
        self.assertEqual(server._round_records(repo), {})          # 프로젝트 카드는 이 라운드를 세지 않는다

    def test_launch_round_requires_ready(self):
        fleet_ctl.set_mode("stopped", "test")
        out = fleet_ctl.launch_round("test")
        self.assertFalse(out["ok"])
        self.assertIn("준비", out["error"])



class ChainTest(unittest.TestCase):
    """이어 달리기 (REV 155) - 목표가 남으면 다음 라운드를 스스로 띄우고, 끝났거나 진전이 없으면 멈춘다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name)
        (self.repo / ".aimem").mkdir()
        (self.repo / "projects" / "알파").mkdir(parents=True)
        for module, attr, value in ((fleet, "ROOT", self.repo), (fleet, "RUNS", self.repo / ".aimem" / "runs"),
                                    (fleet_graph, "GRAPHS", self.repo / ".aimem" / "graph"),
                                    (fleet_ctl, "_aimem_dir", lambda: self.repo / ".aimem")):
            p = mock.patch.object(module, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def progress(self, done, total, extra=""):
        items = "".join(f"- [{'x' if i < done else ' '}] 목표 {i + 1}\n" for i in range(total))
        (self.repo / "projects" / "알파" / "PROGRESS.md").write_text(
            f"# 알파\n\n## 목표\n{items}\n## R7 (2026-11-10)\n- [x] 이건 목표가 아니다\n{extra}", encoding="utf-8")

    def report(self, n, status):
        d = self.repo / "rounds" / f"R{n}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "REPORT.md").write_text(f"# R{n} 종료 보고\n\n**상태: {status}** - 무엇\n", encoding="utf-8")

    def queue(self, *tasks):
        import sqlite3
        con = sqlite3.connect(self.repo / ".aimem" / "aimem.db")
        con.execute("CREATE TABLE IF NOT EXISTS queue(pos INTEGER PRIMARY KEY, task TEXT, slot_hint TEXT, inherited TEXT, note TEXT)")
        con.execute("DELETE FROM queue")
        con.executemany("INSERT INTO queue(pos, task) VALUES(?, ?)", list(enumerate(tasks, 1)))
        con.commit(); con.close()

    def test_queue_is_remaining_fleet_work(self):
        """큐에 일이 남았으면 '끝났습니다' 가 아니다 (2026-11-12 태석님: "큐에 8건은 왜 남았어?")."""
        self.progress(2, 2)
        self.queue("하나", "둘")
        self.assertEqual(fleet_ctl.chain_work(all_=True)["queue"], 2)
        self.assertEqual(fleet_ctl.chain_work(fleet_on=True)["queue"], 2)
        self.assertEqual(fleet_ctl.chain_work(projects=["알파"])["queue"], 0)       # 프로젝트만 고르면 큐는 세지 않는다
        self.assertTrue(fleet_ctl.chain_set(True, all_=True, max_rounds=3)["ok"])
        self.report(7, "DONE")
        self.queue("둘")                                                            # 라운드가 하나를 끝냈다
        d = fleet_ctl.chain_decide(7)
        self.assertEqual((d["action"], d["queue"]), ("launch", 1))
        self.assertIn("큐 1건", d["why"])
        st = fleet_ctl.chain_state(); st["queue_left"] = 1; fleet_ctl._chain_write(st)
        self.report(8, "DONE")
        d = fleet_ctl.chain_decide(8)                                               # 큐가 줄지 않았다
        self.assertEqual((d["action"], d["kind"]), ("stop", "stuck"))
        self.queue()
        d = fleet_ctl.chain_decide(8)
        self.assertEqual((d["action"], d["kind"]), ("stop", "done"))

    def test_queue_request_lists_the_items(self):
        self.queue("로그에 시각 찍기", "검사 고치기")
        ok, res = fleet_ctl._chain_queue_request(7)
        self.assertTrue(ok, res)
        rec = [json.loads(f.read_text(encoding="utf-8")) for f in (self.repo / ".aimem" / "requests").glob("*.json")]
        self.assertEqual(len(rec), 1)
        self.assertIn("큐 2번: 검사 고치기", rec[0]["detail"])
        self.assertFalse(rec[0].get("project"))

    def test_goal_parser_agrees_with_the_monitor(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
        from aimem_monitor import server
        self.progress(2, 5)
        goals = fleet_ctl.project_goals("알파")
        text = (self.repo / "projects" / "알파" / "PROGRESS.md").read_text(encoding="utf-8")
        self.assertEqual({"total": len(goals), "done": sum(1 for d, _ in goals if d)}, server._progress_goals(text))
        self.assertEqual(goals[2], (False, "목표 3"))
        self.assertEqual(fleet_ctl.project_goals("없는것"), [])
        (self.repo / "projects" / "알파" / "PROGRESS.md").write_text(                    # 한 항목이 여러 줄
            "# 알파\n\n## 목표\n- [ ] 기록이 남는다 - 설계 → 구현 → 검수를\n  거친 뒤에만 체크\n  - [x] 하위 항목\n- [x] 둘째\n\n> 인용은 붙이지 않는다\n", encoding="utf-8")
        goals = fleet_ctl.project_goals("알파")
        self.assertEqual(goals[0], (False, "기록이 남는다 - 설계 → 구현 → 검수를 거친 뒤에만 체크"))
        self.assertEqual([d for d, _ in goals], [False, True, True])
        text = (self.repo / "projects" / "알파" / "PROGRESS.md").read_text(encoding="utf-8")
        self.assertEqual({"total": 3, "done": 2}, server._progress_goals(text))

    def test_switching_on_needs_a_sane_cap_and_the_project_is_optional(self):
        st = fleet_ctl.chain_set(True, "", 3, "test")                      # 프로젝트 없이도 켜진다 - 열린 요청이 남은 일이다
        self.assertTrue(st["ok"])
        self.assertEqual((st["chain"]["on"], st["chain"]["all"], st["chain"]["projects"]), (True, True, []))
        fleet_ctl.chain_set(False, by="test")
        self.assertFalse(fleet_ctl.chain_set(True, "../x", 3)["ok"])
        self.assertFalse(fleet_ctl.chain_set(True, "알파", -2)["ok"])              # 0 은 '상한 없이' 라 받는다
        self.assertFalse(fleet_ctl.chain_set(True, "알파", fleet_ctl.CHAIN_MAX_ROUNDS + 1)["ok"])
        self.assertFalse(fleet_ctl.chain_state()["on"])
        self.progress(2, 5)
        st = fleet_ctl.chain_set(True, "알파", 3, "test")["chain"]
        self.assertEqual((st["on"], st["projects"], st["max_rounds"], st["rounds_done"], st["goals_done"]), (True, ["알파"], 3, 0, 2))
        self.assertFalse(fleet_ctl.chain_set(False, by="test")["chain"]["on"])

    def test_decides_to_go_on_only_while_goals_move(self):
        self.assertEqual(fleet_ctl.chain_decide(7)["action"], "stop")              # 꺼져 있다
        self.progress(2, 5)
        fleet_ctl.chain_set(True, "알파", 3, "test")                               # 기준 2/5
        self.assertIn("보고가 없음", fleet_ctl.chain_decide(7)["why"])              # 보고가 없으면 사람이 본다
        self.report(7, "BLOCKED")
        self.assertIn("BLOCKED", fleet_ctl.chain_decide(7)["why"])
        self.report(7, "DONE")
        self.assertIn("늘어난 목표 체크도 없습니다", fleet_ctl.chain_decide(7)["why"])   # 2 → 2
        self.progress(4, 5)
        d = fleet_ctl.chain_decide(7)
        self.assertEqual((d["action"], d["done"], d["total"], d["goals"]["알파"]["open"]), ("launch", 4, 5, ["목표 5"]))
        self.progress(5, 5)
        self.assertIn("끝났습니다", fleet_ctl.chain_decide(7)["why"])
        (self.repo / "projects" / "알파" / "PROGRESS.md").write_text("# 알파\n\n## R7\n- 한 일\n", encoding="utf-8")
        self.assertIn("남은 일이 없습니다", fleet_ctl.chain_decide(7)["why"])       # 목표도 열린 요청도 없다

    def test_round_hit_limit_only_when_graph_log_has_limit_line(self):
        gd = self.repo / ".aimem" / "graph"
        gd.mkdir(parents=True, exist_ok=True)
        (gd / "G-920.json").write_text(
            json.dumps({"id": "G-920", "round": 7, "nodes": []}), encoding="utf-8"
        )
        (gd / "G-920.log").write_text(
            "2026-11-10T22:40:25 retry-queued T-1 rc=1\n", encoding="utf-8"
        )
        self.assertFalse(fleet_ctl._round_hit_limit(7))
        (gd / "G-920.log").write_text(
            "2026-11-10T22:40:25 limit T-1 (R-1) - 사용 한도로 끊김\n", encoding="utf-8"
        )
        self.assertTrue(fleet_ctl._round_hit_limit(7))
        self.assertFalse(fleet_ctl._round_hit_limit(8))

    def test_limit_is_added_to_report_stop_reason_only_when_log_says_limit(self):
        gd = self.repo / ".aimem" / "graph"
        gd.mkdir(parents=True, exist_ok=True)
        (gd / "G-921.json").write_text(
            json.dumps({"id": "G-921", "round": 3, "nodes": []}), encoding="utf-8"
        )
        (gd / "G-921.log").write_text("limit T-1 (R-1) - 사용 한도로 끊김\n", encoding="utf-8")
        fleet_ctl.chain_set(True, None, 3, "t", all_=True)
        self.report(3, "PARTIAL")
        d = fleet_ctl.chain_decide(3)
        self.assertEqual((d["action"], d["kind"]), ("stop", "report"))
        self.assertIn("사용 한도로 끊긴 시도가 있습니다", d["why"])
        (gd / "G-921.log").write_text("spawn T-1 attempt 1 -> R-1\n", encoding="utf-8")
        d = fleet_ctl.chain_decide(3)
        self.assertIn("사람이 봐야 합니다", d["why"])
        self.assertNotIn("사용 한도", d["why"])

    def test_round_hit_limit_swallows_unreadable_graph_or_missing_log(self):
        gd = self.repo / ".aimem" / "graph"
        gd.mkdir(parents=True, exist_ok=True)
        (gd / "G-922.json").write_text("{깨진", encoding="utf-8")
        (gd / "G-922.log").write_text("limit T-1 - 사용 한도로 끊김\n", encoding="utf-8")
        self.assertFalse(fleet_ctl._round_hit_limit(9))
        (gd / "G-923.json").write_text(
            json.dumps({"id": "G-923", "round": 9, "nodes": []}), encoding="utf-8"
        )
        self.assertFalse(fleet_ctl._round_hit_limit(9))

    def req(self, rid, status, project=""):
        d = self.repo / ".aimem" / "requests"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{rid}.json").write_text(json.dumps({"id": rid, "status": status, "project": project, "title": rid}), encoding="utf-8")

    def test_scopes_split_fleet_project_and_all(self):
        """2026-11-11 태석님: "프로젝트를 고를 수 있게 하고, 함대와 all(프로젝트+함대)을 분리해." """
        self.progress(2, 5)                                                    # 알파: 목표 2/5
        (self.repo / "projects" / "베타").mkdir(parents=True)
        (self.repo / "projects" / "베타" / "PROGRESS.md").write_text("# 베타\n\n## 목표\n- [x] 하나\n- [ ] 둘\n", encoding="utf-8")
        (self.repo / "projects" / "목표없음").mkdir(parents=True)
        self.req("Q-f", "NEW"); self.req("Q-a", "PLANNED", "알파"); self.req("Q-b", "NEW", "베타"); self.req("Q-x", "DONE", "알파")
        w = fleet_ctl.chain_work(True, [])
        self.assertEqual((w["requests"], w["goals"]), (["Q-f"], {}))            # 함대 = 프로젝트 없는 요청만
        w = fleet_ctl.chain_work(False, ["알파"])
        self.assertEqual((w["requests"], list(w["goals"])), (["Q-a"], ["알파"]))
        self.assertEqual((w["goals"]["알파"]["done"], w["goals"]["알파"]["total"]), (2, 5))
        w = fleet_ctl.chain_work(False, ["알파", "베타"])                         # 프로젝트 여러 개
        self.assertEqual((sorted(w["requests"]), sorted(w["goals"])), (["Q-a", "Q-b"], ["베타", "알파"]))
        w = fleet_ctl.chain_work(True, ["베타"])                                  # 함대 + 프로젝트 하나
        self.assertEqual(sorted(w["requests"]), ["Q-b", "Q-f"])
        w = fleet_ctl.chain_work(all_=True)
        self.assertEqual((sorted(w["requests"]), sorted(w["goals"])), (["Q-a", "Q-b", "Q-f"], ["베타", "알파"]))
        # 켤 때: 대상 검사
        st = fleet_ctl.chain_set(True, None, 3, "t", projects=["베타", "알파", "알파"])["chain"]
        self.assertEqual((st["all"], st["fleet"], st["projects"], st["label"]), (False, False, ["베타", "알파"], "프로젝트 베타 + 프로젝트 알파"))
        self.assertEqual(fleet_ctl.chain_set(True, "알파", 3, "t")["chain"]["projects"], ["알파"])        # 옛 인자도 받는다
        self.assertTrue(fleet_ctl.chain_set(True, None, 3, "t")["chain"]["all"])                          # 아무것도 안 주면 전체
        st = fleet_ctl.chain_set(True, None, 3, "t", fleet_on=True, projects=[])["chain"]
        self.assertEqual((st["all"], st["fleet"], st["projects"], st["open_requests"], st["goals_done"], st["label"]),
                         (False, True, [], ["Q-f"], 0, "함대"))
        out = fleet_ctl.chain_set(True, None, 3, "t", fleet_on=False, projects=[], all_=False)            # 아무것도 안 고름
        self.assertFalse(out["ok"])
        self.assertIn("하나 이상", out["error"])
        self.assertFalse(fleet_ctl.chain_set(True, None, 3, "t", projects=["../x"])["ok"])
        fleet_ctl.chain_set(True, None, 3, "t", fleet_on=True, projects=[])
        # 함대 범위: 프로젝트 요청이 남아 있어도 함대 요청이 다 닫히면 끝난다
        self.report(7, "DONE"); self.req("Q-f", "DONE")
        self.assertIn("남은 일이 없습니다", fleet_ctl.chain_decide(7)["why"])
        # 전체 범위: 열린 요청이 없는 프로젝트의 남은 목표는 요청으로 넣어 잇는다
        st = fleet_ctl.chain_set(True, None, 4, "t", all_=True)["chain"]
        self.assertEqual((sorted(st["open_requests"]), st["goals_done"]), (["Q-a", "Q-b"], 3))
        self.req("Q-b", "DONE")                                                  # 베타의 요청이 닫혔고 베타 목표 하나가 남았다
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 8}):
            out = fleet_ctl.chain_step(7)
        self.assertTrue(out["launched"])
        self.assertEqual(len(out["filed"]), 1)                                   # 베타만 새 요청 (알파는 열린 요청 Q-a 가 있다)
        new = [json.loads(f.read_text(encoding="utf-8")) for f in (self.repo / ".aimem" / "requests").glob("*.json")
               if json.loads(f.read_text(encoding="utf-8")).get("requester") == "함대 이어 달리기"]
        self.assertEqual([(r["project"], "- 둘" in r["detail"]) for r in new], [("베타", True)])

    def test_the_cap_is_always_kept_and_renewed_in_cycles_when_running_to_the_end(self):
        """2026-11-11 태석님: "끝까지 옵션도 내부적으로는 상한 라운드를 지켜야 해" - 상한에 닿으면 새 묶음으로, 새 관리자로 잇는다."""
        for i in range(1, 8):
            self.req(f"Q-{i}", "NEW")
        st = fleet_ctl.chain_set(True, None, 3, "t", all_=True, renew=True)["chain"]
        self.assertEqual((st["max_rounds"], st["renew"], st["cycles"], st["total_rounds"]), (3, True, 0, 0))
        self.assertFalse(fleet_ctl.chain_set(True, None, 11, "t", all_=True, renew=True)["ok"])      # 상한 자체는 1~10
        self.assertFalse(fleet_ctl.chain_set(True, None, -1, "t", all_=True)["ok"])
        old = fleet_ctl.chain_set(True, None, 0, "t", all_=True)["chain"]                            # 옛 호출: 0 = 기본 상한 + 이어 감
        self.assertEqual((old["max_rounds"], old["renew"]), (fleet_ctl.CHAIN_DEFAULT_ROUNDS, True))
        fleet_ctl.chain_set(True, None, 3, "t", all_=True, renew=True)
        seen = []
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 0}) as launch:
            for n in range(1, 7):                                  # 라운드마다 하나씩 닫힌다
                self.req(f"Q-{n}", "DONE"); self.report(n, "DONE")
                out = fleet_ctl.chain_step(n)
                self.assertTrue(out["launched"], n)
                c = fleet_ctl.chain_state()
                seen.append((c["cycles"], c["rounds_done"], c["total_rounds"]))
            self.req("Q-7", "DONE"); self.report(7, "DONE")
            out = fleet_ctl.chain_step(7)
        # 묶음 안의 라운드 수는 상한(3)을 넘지 않고, 세 번째마다 새 묶음으로 넘어가 0 부터 다시 센다
        self.assertEqual(seen, [(0, 1, 1), (0, 2, 2), (1, 0, 3), (1, 1, 4), (1, 2, 5), (2, 0, 6)])
        self.assertEqual(launch.call_count, 6)
        self.assertIn("남은 일이 없습니다", out["why"])
        log = " ".join(fleet_ctl.chain_state()["log"])
        self.assertIn("새 묶음(2번째)", log)
        # 상한에서 멈추는 방식은 전과 같다
        self.req("Q-8", "NEW"); self.req("Q-9", "NEW")
        fleet_ctl.chain_set(True, None, 1, "t", all_=True)
        self.req("Q-8", "DONE"); self.report(8, "DONE")
        self.assertIn("연속 상한 1 라운드", fleet_ctl.chain_decide(8)["why"])
        # 진전이 없으면 이어 가는 방식이어도 멈춘다
        fleet_ctl.chain_set(True, None, 3, "t", all_=True, renew=True); self.report(9, "DONE")
        self.assertIn("닫힌 요청도", fleet_ctl.chain_decide(9)["why"])
        # 안전 상한 (모두 합친 라운드 수)
        st = fleet_ctl.chain_state(); st["total_rounds"] = fleet_ctl.CHAIN_HARD_ROUNDS - 1; st["open_requests"] = ["Q-9", "Q-old"]
        fleet_ctl._chain_write(st)
        self.assertIn("안전 상한", fleet_ctl.chain_decide(9)["why"])

    def test_autonomous_takes_one_more_round_when_stuck_then_stops(self):
        """2026-11-11 태석님: "완전 자율 종주도 선택 가능하게." 막혀도 한 번은 더 가고, 연달아 두 번 막히면 멈춘다."""
        self.req("Q-1", "NEW"); self.req("Q-2", "NEW")
        st = fleet_ctl.chain_set(True, None, 5, "t", all_=True, autonomous=True)["chain"]
        self.assertEqual((st["autonomous"], st["renew"], st["max_rounds"], st["strikes"]), (True, True, 5, 0))   # 상한은 있고, 닿으면 새로 잇는다
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 0}) as launch:
            self.report(1, "PARTIAL")                                  # 보고가 DONE 이 아니다 - 한 번 더
            out = fleet_ctl.chain_step(1)
            self.assertTrue(out["launched"]); self.assertIn("한 번 더", out["why"])
            self.assertEqual(fleet_ctl.chain_state()["strikes"], 1)
            self.req("Q-1", "DONE"); self.report(2, "DONE")            # 진전 - 스트라이크가 풀린다
            self.assertTrue(fleet_ctl.chain_step(2)["launched"])
            self.assertEqual(fleet_ctl.chain_state()["strikes"], 0)
            self.report(3, "DONE")                                     # 진전 없음 - 한 번 더
            self.assertTrue(fleet_ctl.chain_step(3)["launched"])
            self.report(4, "DONE")                                     # 또 진전 없음 - 멈춘다
            out = fleet_ctl.chain_step(4)
        self.assertEqual(launch.call_count, 3)
        self.assertFalse(out["launched"])
        self.assertIn("연달아 두 번째", out["why"])
        self.assertFalse(fleet_ctl.chain_state()["on"])
        # 자율이 아니면 첫 번째에서 멈춘다 (전과 같다)
        fleet_ctl.chain_set(True, None, 0, "t", all_=True); self.report(5, "BLOCKED")
        self.assertEqual(fleet_ctl.chain_decide(5)["action"], "stop")

    def test_a_stop_records_which_kind_it_was(self):
        """2026-11-11 태석님: 30회 돌고 멈췄는지, 다른 이유인지, 다 끝낸 건지 구별해 알려 줄 것."""
        def stop_kind(setup, n, **kw):
            fleet_ctl.chain_set(True, None, kw.pop("cap", 3), "t", all_=True, **kw)
            setup()
            with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 0}):
                fleet_ctl.chain_step(n)
            st = fleet_ctl.chain_state()
            return st.get("on"), st.get("stopped_kind"), st.get("stopped_round")
        self.req("Q-1", "NEW"); self.req("Q-2", "NEW")
        self.assertEqual(stop_kind(lambda: self.report(1, "BLOCKED"), 1), (False, "report", 1))
        self.assertEqual(stop_kind(lambda: self.report(2, "DONE"), 2), (False, "stuck", 2))                   # 아무것도 안 닫힘
        self.assertEqual(stop_kind(lambda: (self.req("Q-1", "DONE"), self.report(3, "DONE")), 3, cap=1), (False, "cap", 3))
        def to_ceiling():
            st = fleet_ctl.chain_state(); st["total_rounds"] = fleet_ctl.CHAIN_HARD_ROUNDS - 1; st["open_requests"] = ["Q-2", "Q-gone"]
            fleet_ctl._chain_write(st); self.report(4, "DONE")
        self.assertEqual(stop_kind(to_ceiling, 4, renew=True), (False, "safety", 4))
        self.assertEqual(stop_kind(lambda: (self.req("Q-2", "DONE"), self.report(5, "DONE")), 5), (False, "done", 5))
        st = fleet_ctl.chain_state()
        self.assertEqual(st["stopped_left"], {"requests": 0, "goals_done": 0, "goals_total": 0})
        self.assertIn("멈춤[done]", st["log"][-1])
        fleet_ctl.chain_set(False, by="웹(태석)")                                # 스스로 멈춘 뒤에 끄기를 눌러도 까닭을 덮지 않는다
        self.assertEqual(fleet_ctl.chain_state()["stopped_kind"], "done")
        fleet_ctl.chain_set(True, None, 3, "t", all_=True); fleet_ctl.chain_set(False, by="웹(태석)")
        st = fleet_ctl.chain_state()
        self.assertEqual((st["stopped_kind"], "웹(태석)" in st["stopped_why"]), ("off", True))
        self.req("Q-3", "NEW"); fleet_ctl.chain_set(True, None, 3, "t", all_=True); self.req("Q-3", "DONE"); self.req("Q-4", "NEW"); self.report(6, "DONE")
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": False, "error": "이미 실행 중인 관리자가 있습니다"}):
            fleet_ctl.chain_step(6)
        self.assertEqual(fleet_ctl.chain_state()["stopped_kind"], "error")
        self.assertTrue(all(k in fleet_ctl.CHAIN_STOP_KINDS for k in ("done", "cap", "safety", "stuck", "report", "error", "off")))

    def test_open_requests_keep_the_chain_going_without_a_project(self):
        """2026-11-11 태석님: "모든 작업트리 끝내" - 남은 일은 프로젝트 목표만이 아니라 열린 요청이다."""
        self.req("Q-1", "NEW"); self.req("Q-2", "PLANNED"); self.req("Q-3", "DONE")
        st = fleet_ctl.chain_set(True, None, 3, "test")["chain"]
        self.assertEqual(st["open_requests"], ["Q-1", "Q-2"])
        self.report(7, "DONE")
        self.assertIn("닫힌 요청도", fleet_ctl.chain_decide(7)["why"])              # 아무것도 안 닫혔다 - 멈춘다
        self.req("Q-1", "DONE")                                                      # 하나 닫혔고 하나 남았다
        d = fleet_ctl.chain_decide(7)
        self.assertEqual((d["action"], d["requests"]), ("launch", ["Q-2"]))
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 8}) as launch:
            out = fleet_ctl.chain_step(7)
        launch.assert_called_once()
        self.assertTrue(out["launched"])
        self.assertEqual(len(list((self.repo / ".aimem" / "requests").glob("*.json"))), 3)     # 요청을 새로 넣지 않는다
        self.assertEqual(fleet_ctl.chain_state()["open_requests"], ["Q-2"])
        self.req("Q-2", "DONE"); self.report(8, "DONE")
        with mock.patch.object(fleet_ctl, "launch_round") as launch:
            out = fleet_ctl.chain_step(8)
        launch.assert_not_called()
        self.assertIn("남은 일이 없습니다", out["why"])
        self.assertFalse(fleet_ctl.chain_state()["on"])

    def test_step_files_a_request_launches_and_stops_at_the_cap(self):
        self.progress(1, 5)
        fleet_ctl.chain_set(True, "알파", 2, "test")
        self.progress(3, 5)
        self.report(7, "DONE")
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": True, "round": 8}) as launch:
            out = fleet_ctl.chain_step(7)
        launch.assert_called_once()
        self.assertEqual((out["launched"], out["round"]), (True, 8))
        reqs = list((self.repo / ".aimem" / "requests").glob("*.json"))
        self.assertEqual(len(reqs), 1)
        rec = json.loads(reqs[0].read_text(encoding="utf-8"))
        self.assertEqual((rec["project"], rec["status"], rec["requester"]), ("알파", "NEW", "함대 이어 달리기"))
        self.assertIn("- 목표 4", rec["detail"])
        self.assertNotIn("- 목표 1", rec["detail"])
        st = fleet_ctl.chain_state()
        self.assertEqual((st["on"], st["rounds_done"], st["goals_done"]), (True, 1, 3))
        # 두 번째 라운드가 끝났다 - 목표는 늘었지만 연속 상한 2 에 닿았다
        self.progress(4, 5)
        self.report(8, "DONE")
        with mock.patch.object(fleet_ctl, "launch_round") as launch:
            out = fleet_ctl.chain_step(8)
        launch.assert_not_called()
        self.assertFalse(out["launched"])
        self.assertIn("연속 상한", out["why"])
        st = fleet_ctl.chain_state()
        self.assertFalse(st["on"])
        self.assertIn("연속 상한", st["stopped_why"])
        self.assertEqual(len(list((self.repo / ".aimem" / "requests").glob("*.json"))), 1)   # 멈출 땐 요청을 안 넣는다

    def test_the_web_endpoint_switches_it_and_validates_the_body(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
        from aimem_monitor import server
        self.progress(1, 5)
        with mock.patch.object(server, "ROOT", self.repo.resolve()):
            for bad in (None, {}, {"on": "yes"}, {"on": 1}):
                code, out = server.fleet_action("chain", "웹(test)", self.repo, bad)
                self.assertEqual((code, out["ok"]), (400, False), bad)
            code, out = server.fleet_action("chain", "웹(test)", self.repo, {"on": True, "project": "../x", "max_rounds": 3})
            self.assertEqual(code, 400)
            code, out = server.fleet_action("chain", "웹(test)", self.repo, {"on": True, "project": "알파", "max_rounds": 4})
            self.assertEqual((code, out["chain"]["on"], out["chain"]["max_rounds"], out["chain"]["by"]), (200, True, 4, "웹(test)"))
            self.assertTrue(fleet_ctl.public_state()["chain"]["on"])
            code, out = server.fleet_action("chain", "웹(test)", self.repo, {"on": False})
            self.assertEqual((code, out["chain"]["on"]), (200, False))
        code, out = server.fleet_action("chain", "웹(test)", self.repo, {"on": True, "project": "알파"})   # 운영 저장소가 아니면 거절
        self.assertEqual(code, 409)

    def test_last_round_summary_comes_from_the_relay_record_and_report(self):
        """끝난 관리자 세션은 게이트웨이 목록에서 사라져 화면이 R6 을 최근 관리자로 보였다 (R7~R11)."""
        with mock.patch.object(fleet_ctl, "_manager_sessions", return_value=[]):
            self.assertIsNone(fleet_ctl.public_state()["last_round"])
            (self.repo / ".aimem" / "relay").mkdir()
            (self.repo / ".aimem" / "relay" / "r11.json").write_text(json.dumps(
                {"round": 11, "label": "관리자 R11 (Opus) 2026-11-11", "at": "2026-11-11T15:38:08", "state": "spawned"}), encoding="utf-8")
            lr = fleet_ctl.public_state()["last_round"]
            self.assertEqual((lr["round"], lr["label"], lr["report_status"], lr["report"]), (11, "관리자 R11 (Opus) 2026-11-11", None, None))
            self.report(11, "DONE")
            lr = fleet_ctl.public_state()["last_round"]
            self.assertEqual((lr["report_status"], lr["report"]), ("DONE", "rounds/R11/REPORT.md"))

    def test_an_hours_old_manager_list_is_not_served_as_current(self):
        """아무도 화면을 안 보면 갱신이 안 돈다 - 묵은 목록을 그대로 내주면 끝난 관리자가 '실행 중' 으로 보였다 (R9 실측)."""
        import datetime
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
        from aimem_monitor import server
        old_list = {"ok": True, "sessions": [{"label": "관리자 R8", "status": "running"}], "error": None}
        with mock.patch.object(server, "_refresh_managers"), \
             mock.patch.dict(server._mgr_cache, {"at": datetime.datetime.now() - datetime.timedelta(hours=2), "value": old_list, "refreshing": False}):
            out = server.manager_status(server.ROOT)
            self.assertEqual((out["sessions"], out["pending"]), ([], True))
            self.assertGreater(out["age_sec"], 7000)
        with mock.patch.object(server, "_refresh_managers"), \
             mock.patch.dict(server._mgr_cache, {"at": datetime.datetime.now() - datetime.timedelta(seconds=50), "value": old_list, "refreshing": False}):
            out = server.manager_status(server.ROOT)                       # 조금 낡은 것은 그대로 보이고 배경에서 갱신한다
            self.assertEqual((len(out["sessions"]), out["pending"]), (1, False))

    def test_a_launch_that_fails_switches_the_chain_off(self):
        self.progress(1, 5)
        fleet_ctl.chain_set(True, "알파", 5, "test")
        self.progress(2, 5)
        self.report(7, "DONE")
        with mock.patch.object(fleet_ctl, "launch_round", return_value={"ok": False, "error": "이미 실행 중인 관리자가 있습니다"}):
            out = fleet_ctl.chain_step(7)
        self.assertFalse(out["launched"])
        self.assertFalse(fleet_ctl.chain_state()["on"])
        self.assertIn("관리자", fleet_ctl.chain_state()["stopped_why"])


if __name__ == "__main__":
    unittest.main()


class CanStopTest(unittest.TestCase):
    """`can.stop` 은 죽일 것이 있을 때만 (2026-11-10 점검 5번)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)
        (self.tmp / "runs").mkdir()
        (self.tmp / "graph").mkdir()
        for module, attr, value in ((fleet, "RUNS", self.tmp / "runs"), (fleet_graph, "GRAPHS", self.tmp / "graph"),
                                    (fleet_ctl, "_aimem_dir", lambda: self.tmp)):
            p = mock.patch.object(module, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def test_next_round_can_be_launched_right_after_a_round_ends(self):
        """2026-11-11 태석님: 라운드가 끝나면 '실행' 으로 남아 '준비' 도 '라운드 실행' 도 꺼져 있었고,
        일시 중지 → 준비 → '실행' 을 누르면 다시 그 상태로 돌아가 새 요청이 처리되지 않았다."""
        repo = self.tmp / "repo"
        (repo / ".aimem" / "briefs").mkdir(parents=True)
        (repo / ".aimem" / "briefs" / fleet_ctl.STANDARD_BRIEF).write_text("x", encoding="utf-8")
        with mock.patch.object(fleet, "ROOT", repo), mock.patch.object(fleet_ctl, "_manager_sessions", return_value=[]):
            fleet_ctl.set_mode("running", "test")                       # 라운드가 끝난 뒤의 상태
            st = fleet_ctl.public_state()
            self.assertTrue(st["idle"])
            self.assertEqual((st["can"]["round"], st["can"]["prepare"], st["can"]["run"]), (True, True, False))
            self.assertTrue(fleet_ctl.round_over())
            # 관리자가 아직 살아 있으면 끝난 것이 아니다
            st = fleet_ctl.public_state(manager_running_now=True)
            self.assertEqual((st["idle"], st["can"]["round"], st["can"]["prepare"]), (False, False, False))
            # 전달 중(세션이 아직 안 보이는 구간)에도 끝난 것이 아니다 - 두 번 띄우지 않게
            (self.tmp / "relay").mkdir()
            (self.tmp / "relay" / "r9.json").write_text(json.dumps({"round": 9, "state": "relaying"}), encoding="utf-8")
            st = fleet_ctl.public_state()
            self.assertEqual((st["idle"], st["can"]["round"]), (False, False))
            self.assertFalse(fleet_ctl.round_over())
            (self.tmp / "relay" / "r9.json").write_text(json.dumps({"round": 9, "state": "spawned"}), encoding="utf-8")
            self.assertTrue(fleet_ctl.public_state()["idle"])
            # 준비 상태에서 이을 것이 없으면 '실행' 은 모드를 바꾸지 않는다 (바꾸면 '라운드 실행' 이 꺼진다)
            fleet_ctl.set_mode("ready", "test")
            st = fleet_ctl.public_state()
            self.assertEqual((st["idle"], st["can"]["run"], st["can"]["round"]), (False, False, True))
            out = fleet_ctl.resume("test")
            self.assertFalse(out["ok"])
            self.assertIn("라운드 실행", out["error"])
            self.assertEqual(fleet_ctl.mode(), "ready")
            # 멈춘 뒤에는 '실행' 이 전처럼 풀어 준다
            fleet_ctl.set_mode("paused", "test")
            self.assertTrue(fleet_ctl.public_state()["can"]["run"])
            self.assertTrue(fleet_ctl.resume("test")["ok"])
            self.assertEqual(fleet_ctl.mode(), "running")

    def test_launch_from_a_finished_round_runs_the_readiness_check_first(self):
        fleet_ctl.set_mode("running", "test")
        failing = {"ok": False, "mode": "running", "checks": [{"name": "실행 중인 관리자 없음", "ok": False, "detail": "관리자 R9", "required": True}]}
        with mock.patch.object(fleet_ctl, "prepare", return_value=failing) as prep:
            out = fleet_ctl.launch_round("test")
        prep.assert_called_once()
        self.assertFalse(out["ok"])
        self.assertIn("실행 중인 관리자 없음", out["error"])
        self.assertEqual(fleet_ctl.mode(), "running")
        fleet_ctl.set_mode("paused", "test")                           # 멈춘 상태에서는 전처럼 거절 (점검도 안 돌린다)
        with mock.patch.object(fleet_ctl, "prepare") as prep:
            out = fleet_ctl.launch_round("test")
        prep.assert_not_called()
        self.assertFalse(out["ok"])

    def test_stop_only_when_something_is_running(self):
        fleet_ctl.set_mode("ready", "test")
        self.assertFalse(fleet_ctl.public_state()["can"]["stop"])
        fleet_ctl.set_mode("stopped", "test")
        self.assertFalse(fleet_ctl.public_state()["can"]["stop"])
        fleet_ctl.set_mode("running", "test")
        self.assertTrue(fleet_ctl.public_state()["can"]["stop"])
        fleet_ctl.set_mode("paused", "test")
        self.assertTrue(fleet_ctl.public_state()["can"]["stop"])
