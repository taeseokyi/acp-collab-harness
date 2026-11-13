#!/usr/bin/env python3
"""모니터가 그래프 러너의 새 상태(공급자 대기·기반 장애·실패 종류)를 보여 주는지 브라우저로 잽니다.

임시 저장소에 그래프 JSON 과 보드 DB 를 꾸민다. 진짜 하네스는 뜨지 않는다.
"""
import _fleet_env  # noqa: F401
import contextlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from unittest import mock
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server  # noqa: E402
import _monitor_fixture  # noqa: E402


class Checks:
    def __init__(self): self.results = []
    def ok(self, goal, cond, detail=""): self.results.append((bool(cond), goal, detail))
    def finish(self):
        failures = sum(not p for p, _, _ in self.results)
        for p, goal, detail in self.results:
            print(f"[{'OK' if p else 'FAIL'}] {goal}" + (f" - {detail}" if detail else ""))
        print(f"통과 {len(self.results) - failures} / 전체 {len(self.results)}")
        return failures


@contextmanager
def temp_db(root):
    import aimem_db
    import fleet
    targets = ((fleet, "RUNS", root / ".aimem" / "runs"), (fleet, "ROOT", root), (aimem_db, "ROOT", root),
               (aimem_db, "DB", root / ".aimem" / "aimem.db"), (aimem_db, "AIMEM", root / "AIMEM.md"),
               (aimem_db, "HANDOFF", root / ".aimem" / "handoff.md"), (server, "ROOT", root))
    patches = [mock.patch.object(t, a, v) for t, a, v in targets]
    try:
        for p in patches: p.start()
        with contextlib.redirect_stdout(io.StringIO()):
            aimem_db.cmd_init()
        yield
    finally:
        for p in patches: p.stop()


def node(i, status, **kw):
    n = {"id": i, "title": "노드 " + i, "slot": "S2", "harness": "claude", "status": status, "deps": [],
         "attempts": [], "max_attempts": 2}
    n.update(kw)
    return n


def build(root):
    gd = root / ".aimem" / "graph"
    gd.mkdir(parents=True)
    now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    att = lambda rid, **kw: dict({"run_id": rid, "fail_kind": None}, **kw)  # noqa: E731
    nodes = [
        node("N1", "todo", waiting="provider:kisti"),
        node("N2", "todo", waiting="provider:kisti"),
        node("N3", "todo", waiting="probe:kisti", infra_attempts=[att("N3-S2-a1", fail_kind="infra", provider="kisti")]),
        node("N4", "todo", waiting="slot:S2"),
        node("N5", "blocked", infra=True, infra_attempts=[att("N5-S2-a1", fail_kind="infra", why="침묵"),
                                                        att("N5-S2-a2", fail_kind="infra", session_state="stalled", why="재접속 오류"),
                                                        att("N5-S2-a3", fail_kind="infra")]),
        node("N6", "failed", attempts=[att("N6-S2-a1", fail_kind="work"), att("N6-S2-a2", fail_kind="limit"),
                                        att("N6-S2-a3", fail_kind="timeout", session_state="stalled", why="시간 초과로 끊음")]),
        node("N7", "done", attempts=[att("N7-S2-a1")]),
    ]
    (gd / "G-1.json").write_text(json.dumps({"id": "G-1", "request": "그래프 상태 검사", "created": now, "updated": now,
                                              "nodes": nodes}, ensure_ascii=False), encoding="utf-8")
    # 끝나지 않았는데 실행기가 없는 그래프 - 대기 요약에 들지 않고 '실행기 없음' 으로 보인다
    (gd / "G-2.json").write_text(json.dumps({"id": "G-2", "request": "실행기 없는 그래프", "created": now, "updated": now,
                                              "nodes": [node("M1", "todo", waiting="provider:kisti")]}, ensure_ascii=False), encoding="utf-8")
    con = sqlite3.connect(str(root / ".aimem" / "aimem.db"))
    for tid, st in (("N1", "TODO"), ("N5", "BLOCKED"), ("N6", "BLOCKED"), ("N7", "REVIEW")):
        con.execute("INSERT OR REPLACE INTO tasks(id, title, slot, status, inherited, artifacts, created, updated)"
                    " VALUES (?,?,?,?,?,?,?,?)", (tid, "노드 " + tid, "S2", st, "", "", now, now))
    con.commit(); con.close()


FLEET = {"mode": "running", "label": "실행", "default": False, "idle": False, "running_runs": 0, "graphs": [],
         "can": {}, "brief": {}, "manager": None}


def scenario(browser, base, checks, width):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector(".fc-head", timeout=15000)
        page.wait_for_selector("#graphs-list .graph-block", state="attached", timeout=15000)
        page.wait_for_timeout(300)
        fc = page.locator("#fleet-control").inner_text()
        checks.ok(f"[{width}] 함대 요약: 공급자 kisti 자리 대기 2건 (실행기 없는 G-2 의 대기는 빼고)", "공급자 kisti 자리 대기 2건" in fc, fc[:200])
        checks.ok(f"[{width}] 함대 요약: 공급자 장애로 멈춘 노드 1건", "공급자 장애로 멈춘 노드 1건" in fc)
        sw = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        checks.ok(f"[{width}] 함대 탭 가로 넘침 없음", sw <= 0, str(sw))
        page.click("#tab-requests")
        page.wait_for_selector("#graphs-list .graph-block", state="visible", timeout=15000)
        def badge_of(gid):
            return page.locator("#graphs-list .graph-block", has_text=gid).first.locator(".graph-head .badge").inner_text().strip()
        checks.ok(f"[{width}] 실행기가 잡은 그래프는 '실행 중'", badge_of("G-1") == "실행 중", badge_of("G-1"))
        checks.ok(f"[{width}] 실행기 없는 미완 그래프는 '실행기 없음'", badge_of("G-2") == "실행기 없음", badge_of("G-2"))
        g2 = page.locator("#graphs-list .graph-block", has_text="G-2").first.locator(".graph-head .graph-meta").inner_text()
        checks.ok(f"[{width}] 실행기 없으면 남은 시간을 말하지 않는다", "남은" not in g2, g2)
        c1 = page.locator("#graphs-list .graph-block", has_text="G-1").first.locator(".graph-counts").inner_text()
        checks.ok(f"[{width}] 개수 줄: 공급자 장애는 막힘과 따로", "공급자 장애 1" in c1 and "막힘" not in c1 and "실패 1" in c1, c1)
        notes = page.locator("#graphs-list .graph-note")
        by = {}
        for i in range(notes.count()):
            li = notes.nth(i)
            by.setdefault(li.get_attribute("data-node"), []).append(li.inner_text())
        j = lambda k: " | ".join(by.get(k, []))  # noqa: E731
        checks.ok(f"[{width}] 공급자 대기 메모", "공급자 대기 (kisti)" in j("N1"), j("N1"))
        checks.ok(f"[{width}] 공급자 응답 대기 메모 + 장애 재시도 1", "공급자 응답 대기 (kisti)" in j("N3") and "장애 재시도 1" in j("N3"), j("N3"))
        checks.ok(f"[{width}] 슬롯 대기 메모", "슬롯 대기 (S2)" in j("N4"), j("N4"))
        checks.ok(f"[{width}] 장애 막힘: 안내 한 줄 + 장애 재시도 3", "태스크 잘못이 아닙니다 - 공급자가 돌아오면 unblock" in j("N5") and "장애 재시도 3" in j("N5"), j("N5"))
        n5 = page.locator("#graphs-list tbody tr", has_text="N5").first.locator(".badge")
        checks.ok(f"[{width}] 장애 막힘 배지 '공급자 장애'", n5.inner_text().strip() == "공급자 장애", n5.inner_text())
        n6 = page.locator("#graphs-list tbody tr", has_text="N6").first.locator(".badge")
        checks.ok(f"[{width}] 작업 실패는 '실패'", n6.inner_text().strip() == "실패", n6.inner_text())
        checks.ok(f"[{width}] 끝난 노드엔 메모 없음", "N7" not in by and "N6" not in by)
        sw = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        checks.ok(f"[{width}] 가로 넘침 없음", sw <= 0, str(sw))
        if width == 1280:
            page.locator("#graphs-list tbody tr", has_text="N6").first.click()
            page.wait_for_selector("#detail-body .attempt-item", state="attached", timeout=5000); page.wait_for_timeout(300)
            body = page.locator("#detail-body").inner_text()
            checks.ok("N6 시도 목록: 작업 실패·사용 한도·시간 초과·세션 stalled·why",
                      all(w in body for w in ("작업 실패", "사용 한도", "시간 초과", "stalled", "시간 초과로 끊음")), body[-300:])
            page.locator("#detail-close").click()
            page.locator("#graphs-list tbody tr", has_text="N5").first.click()
            page.wait_for_selector("#detail-body .attempt-item", state="attached", timeout=5000); page.wait_for_timeout(300)
            body = page.locator("#detail-body").inner_text()
            checks.ok("N5 상세: 공급자 장애 시도·안내", "공급자 장애" in body and "unblock" in body and "재접속 오류" in body, body[-300:])
            page.locator("#detail-close").click()
            # 보드는 DB 값 그대로 (그래프 노드 상태로 바꿔 보여 주지 않는다)
            page.click("#tab-board")
            page.wait_for_selector("#board-filter button", state="visible", timeout=15000)
            page.locator("#board-filter button", has_text="전체").click()
            def st(t):
                return page.locator("#board-section tbody tr", has_text=t).first.locator(".badge").first.get_attribute("data-status")
            checks.ok("보드: N1 은 DB 값 TODO 그대로 (노드는 todo)", st("N1") == "TODO", str(st("N1")))
            checks.ok("보드: N7 은 REVIEW 그대로 (노드는 done)", st("N7") == "REVIEW", str(st("N7")))
            checks.ok("보드: N6 은 BLOCKED", st("N6") == "BLOCKED", str(st("N6")))
            page.locator("#board-filter button", has_text="미완료").click()
            checks.ok("미완료 칩에 REVIEW 포함 (4건)", "미완료 4" in page.locator("#board-filter").inner_text(), page.locator("#board-filter").inner_text())
        checks.ok(f"[{width}] 자바스크립트 오류 없음", not errors, "; ".join(errors)[:200])
    finally:
        ctx.close()


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="graphstates-")).resolve()
    (root / ".aimem").mkdir()
    checks = Checks()
    with temp_db(root):
        build(root)
        with mock.patch.object(server, "fleet_state", lambda *a, **k: FLEET), \
                mock.patch.object(server, "_fleet_ctl", return_value=mock.Mock(graphs_overview=lambda: [
                    {"id": "G-1", "runner": 4242}, {"id": "G-2", "runner": None}])), \
                _monitor_fixture.serve(server, root) as (_, base), sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for w in (1280, 360):
                    scenario(browser, base, checks, w)
            finally:
                browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
