#!/usr/bin/env python3
"""모니터의 관리자 카드·세션 실행 표시를 브라우저에서 잽니다 (openclaw 없는 체제, 설계 5.6).

임시 저장소에 관리자·작업자 세션 폴더를 꾸미고, 카드 문구·마지막 사건·침묵 배지·상세 패널을 본다.
진짜 하네스는 뜨지 않는다 (`_fleet_env`).
"""
import _fleet_env  # noqa: F401
import datetime as dt
import http.server
import json
import pathlib
import sys
import tempfile
import threading
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server  # noqa: E402
from fleet_rt import sessions  # noqa: E402


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
def monitor_server(root):
    handler = type("H", (server.Handler,), {"root": root, "require_auth": False, "tls": False,
                                            "access_token": None, "guard": server.LoginGuard(),
                                            "timeout": 5, "log_message": lambda *a, **k: None})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=3)


def ev(**kw): return json.dumps(kw, ensure_ascii=False)


def mk(root, sid, role, *, running=False, end=None, events=(), report=None, extra_meta=None):
    sroot = root / ".aimem" / "sessions"
    d = sroot / sid
    d.mkdir(parents=True)
    now = dt.datetime.now()
    meta = {"id": sid, "role": role, "harness": "fake", "model": "opus", "provider": "anthropic", "round": 21,
            "label": "R21 관리자" if role == "manager" else "T-1 작업", "started": (now - dt.timedelta(minutes=9)).isoformat(timespec="seconds"),
            "extra": {}}
    if role == "worker":
        meta.update({"slot": "S2", "task_id": "T-1"})
    meta.update(extra_meta or {})
    if running:
        pid = _fleet_env.marked_pid(sroot, sid)
        meta["supervisor_pid"], meta["proc_start"] = pid, sessions.proc_start(pid)
    else:
        meta["supervisor_pid"] = 2 ** 22 + 777
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "brief.md").write_text("지시문", encoding="utf-8")
    lines = [(now - dt.timedelta(seconds=a)).isoformat(timespec="seconds") + "\t" + raw for a, raw in events]
    if lines:
        (d / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if report is not None:
        (d / "report.md").write_text(report, encoding="utf-8")
    if end is not None:
        (d / "end.json").write_text(json.dumps(end), encoding="utf-8")


def scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#manager-card .manager-label", timeout=8000)
        card = page.locator("#manager-card").inner_text()
        checks.ok("관리자 카드가 실행 중 세션을 보인다", "실행 중" in card and "R21 관리자" in card, card[:120])
        checks.ok("'조회 중' 이 없다", "조회 중" not in card, card[:60])
        checks.ok("마지막 사건과 최근 단계가 보인다", "마지막 사건" in card and "Bash: ls" in card, card[:200])
        checks.ok("작업자 실행 표에 '마지막 사건 N초 전 · ...' 이 보인다",
                  page.locator(".run-last-event").count() >= 1 and "[tool]" in page.locator(".run-last-event").first.inner_text())
        txt = page.locator("#runs-table-wrap").inner_text()
        checks.ok("침묵으로 끊긴 실행은 '침묵으로 끊김' 배지", "침묵으로 끊김" in txt, txt[:160])
        checks.ok("시간 초과 실행은 '시간 초과' 배지", "시간 초과" in txt)
        page.locator(".manager-detail-btn").click()
        page.wait_for_selector("#detail-body .mgr-list", timeout=5000)
        body = page.locator("#detail-body").inner_text()
        checks.ok("관리자 상세: 라운드 기록·단계 (실행 중이라 마지막 보고는 아직 없다)", "라운드 R21 기록" in body and "최근 단계" in body, body[:200])
        checks.ok("관리자 상세에 전달(relay)·클로 문구가 없다", "전달" not in body and "클로" not in body)
        page.keyboard.press("Escape")
        # 작업자 실행 상세: 사건 블록 (접힘)
        page.locator("#runs-table-wrap tbody tr", has_text="T-1-S2-a1-110000").first.click()
        page.wait_for_selector("#detail-body details", timeout=5000)
        summ = page.locator("#detail-body details summary").all_inner_texts()
        checks.ok("실행 상세에 접힌 '사건' 블록", any("사건" in s for s in summ), str(summ))
        checks.ok("사건 블록은 기본 접힘", page.locator("#detail-body details[open]").count() == 0)
        checks.ok("자바스크립트 오류 없음", not errors, "; ".join(errors)[:200])
    finally:
        ctx.close()


def fleet_manager_scenario(browser, base, checks, state):
    """`fleet_ctl.public_state()` 의 `manager` 키 (launching|running|failed) 가 함대 카드·관리자 카드에 어떻게 보이나."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#fleet-card .fc-head, #fleet-control .fc-head, .fc-head", timeout=8000)
        page.wait_for_timeout(300)
        txt = page.locator("body").inner_text()
        checks.ok(f"함대 카드 manager={state}", {"launching": "관리자를 띄우는 중", "running": "관리자 R21 실행 중 · 마지막 사건",
                                                 "failed": "R21 관리자: 실패"}[state] in txt, state)
        checks.ok(f"{state}: 클로·전달 문구 없음", "클로" not in txt and "클로에게" not in txt)
        checks.ok(f"{state}: 자바스크립트 오류 없음", not errors, "; ".join(errors)[:200])
    finally:
        ctx.close()


def calls_root(*, running):
    """호출 방식 라운드 R23: ① 계획, ② 판정 둘 (running 이면 둘째 판정이 도는 중)."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="mgr-calls-"))
    (root / ".aimem").mkdir()
    now = dt.datetime.now()
    def ago(m): return (now - dt.timedelta(minutes=m)).isoformat(timespec="seconds")
    def meta(phase, m, lab): return {"round": 23, "label": f"관리자 R23 {lab} (Opus) 2026-11-13", "started": ago(m), "extra": {"phase": phase}}
    done = lambda: {"state": "done", "rc": 0, "ended": ago(1), "fail_kind": None, "why": None}
    mk(root, "M-R23-110000", "manager", end=done(), extra_meta=meta("plan", 30, "① 계획"))
    mk(root, "M-R23-111000", "manager", end=done(), extra_meta=meta("judge", 20, "② 판정"))
    mk(root, "M-R23-112000", "manager", running=running, end=None if running else done(),
       events=[(20, ev(type="tool", name="Bash", summary="ls"))] if running else (), extra_meta=meta("judge", 10, "② 판정"))
    return root


def calls_fleet_state(st, phase, calls):
    return {"mode": "running", "label": "실행", "default": False, "idle": False, "running_runs": 0, "graphs": [],
            "can": {a: False for a in server.FLEET_ACTIONS}, "brief": {"round": 24, "file": "x.md", "standard": True},
            "manager": {"round": 23, "label": "관리자 R23", "session": "M-R23-112000", "state": st, "by": "t",
                        "at": "2026-11-13T11:00:00", "ended": None, "brief": "x.md", "workspace": "rounds/R23",
                        "last_event_at": (dt.datetime.now() - dt.timedelta(seconds=5)).isoformat(timespec="seconds"),
                        "mode": "calls", "phase": phase, "calls": calls}}


def calls_scenario(browser, base, checks, name, want, *, driving=False, width=1280):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#manager-card .manager-label", timeout=8000)
        page.wait_for_timeout(300)
        txt = page.locator("body").inner_text()
        checks.ok(f"{name}: 함대 카드 문구", want in txt, want)
        checks.ok(f"{name}: 자바스크립트 오류 없음", not errors, "; ".join(errors)[:200])
        card = page.locator("#manager-card")
        checks.ok(f"{name}: 관리자 카드에 'R23 ② 판정'", "R23 ② 판정" in card.inner_text(), card.inner_text()[:160])
        if driving:
            checks.ok(f"{name}: driving 배지", page.locator("#manager-card [data-status=driving]").count() == 1
                      and "엔진이 그래프 실행 중" in card.inner_text())
            checks.ok(f"{name}: driving 배지는 running 색", "running" in (page.locator("#manager-card [data-status=driving]").first.get_attribute("class") or ""))
        else:
            checks.ok(f"{name}: running 배지", page.locator("#manager-card [data-status=running]").count() == 1)
        if width <= 400:
            ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            checks.ok(f"{name}: 가로 넘침 없음({width}px)", ov <= 0, str(ov))
        card.get_by_text("세션 목록").click()
        page.wait_for_selector(".manager-round-head", timeout=5000)
        panel = page.locator("body").inner_text()
        checks.ok(f"{name}: 목록에 라운드 머리글·단계", "R23 · 호출 3개" in panel and "R23 ① 계획" in panel and "R23 ② 판정" in panel)
        if width <= 400:
            ov = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            checks.ok(f"{name}: 목록 가로 넘침 없음({width}px)", ov <= 0, str(ov))
        page.locator("#detail-body tbody tr", has_text="R23 ① 계획").first.click()
        page.wait_for_selector("#detail-body .detail-meta", timeout=5000)
        checks.ok(f"{name}: 상세 제목에 단계", "① 계획" in page.locator("#detail-label").inner_text(), page.locator("#detail-label").inner_text())
    finally:
        ctx.close()


def resident_unchanged(browser, base, checks, fs):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#manager-card .manager-label", timeout=8000)
        page.wait_for_timeout(300)
        checks.ok("상주 라운드: 단계 표시·호출 문구 없음", page.locator(".manager-phase").count() == 0
                  and "호출" not in page.locator("#manager-card").inner_text()
                  and "호출 중" not in page.locator("body").inner_text())
        page.locator("#manager-card").get_by_text("세션 목록").count()
        checks.ok("상주 라운드: 라운드 머리글 없음", page.locator(".manager-round-head").count() == 0)
    finally:
        ctx.close()


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="mgr-browser-"))
    (root / ".aimem").mkdir()
    mk(root, "M-R21-110000", "manager", running=True, events=[
        (200, ev(type="text", text="상태를 읽습니다")), (30, ev(type="tool", name="Bash", summary="ls tools"))])
    mk(root, "T-1-S2-a1-110000", "worker", running=True, events=[
        (100, ev(type="text", text="시작")), (12, ev(type="tool", name="Bash", summary="python3 x.py"))])
    mk(root, "T-2-S2-a1-110000", "worker", end={"state": "stalled", "rc": 125, "ended": dt.datetime.now().isoformat(timespec="seconds"),
                                                "fail_kind": "infra", "why": "침묵"}, report="BLOCKED")
    mk(root, "T-3-S2-a1-110000", "worker", end={"state": "timeout", "rc": 124, "ended": dt.datetime.now().isoformat(timespec="seconds"),
                                                "fail_kind": "timeout", "why": "시간"}, report="BLOCKED")
    rd = root / "rounds" / "R21"; rd.mkdir(parents=True)
    (rd / "round.json").write_text(json.dumps({"round": 21, "at": "2026-11-12T11:00:00", "brief": "manager-round-standard.md",
                                               "requests": ["Q-1"], "projects": []}), encoding="utf-8")
    checks = Checks()
    with monitor_server(root) as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            scenario(browser, base, checks)
            from unittest import mock
            for st in ("launching", "running", "failed"):
                m = {"round": 21, "label": "R21 관리자", "session": "M-R21-110000", "state": st, "by": "t", "at": "2026-11-12T11:00:00",
                     "ended": None, "brief": "x.md", "workspace": "rounds/R21",
                     "last_event_at": (dt.datetime.now() - dt.timedelta(seconds=5)).isoformat(timespec="seconds")}
                fs = {"mode": "running", "label": "실행", "default": False, "idle": False, "running_runs": 0, "graphs": [],
                      "can": {a: False for a in server.FLEET_ACTIONS}, "brief": {"round": 22, "file": "x.md", "standard": True},
                      "manager": m}
                with mock.patch.object(server, "fleet_state", lambda *a, **k: fs):
                    fleet_manager_scenario(browser, base, checks, st)
                if st == "running":
                    with mock.patch.object(server, "fleet_state", lambda *a, **k: fs):
                        resident_unchanged(browser, base, checks, fs)
        finally:
            browser.close()
    from unittest import mock
    cases = [("계획 호출", "running", "plan", 1, "R23 ① 계획 호출 중 · 마지막 사건", False),
             ("판정 호출", "running", "judge", 3, "R23 ② 판정 호출 중 (3번째 호출)", False),
             ("마감 호출", "running", "close", 4, "R23 ③ 마감 호출 중", False),
             ("호출 사이", "driving", "judge", 3, "R23 호출 사이 - 엔진이 그래프를 돌리는 중 (마지막 호출: ② 판정)", True)]
    for width in (1280, 360):
        for nm, st, ph, n, want, drv in cases:
            root2 = calls_root(running=not drv)
            fs = calls_fleet_state(st, ph, n)
            with monitor_server(root2) as base2, sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    with mock.patch.object(server, "fleet_state", lambda *a, **k: fs):
                        calls_scenario(browser, base2, checks, f"{nm}@{width}", want, driving=drv, width=width)
                finally:
                    browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
