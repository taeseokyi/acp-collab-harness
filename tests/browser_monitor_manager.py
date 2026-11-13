#!/usr/bin/env python3
"""모니터의 관리자 카드·세션 실행 표시를 브라우저에서 잽니다 (openclaw 없는 체제, 설계 5.6).

임시 저장소에 관리자·작업자 세션 폴더를 꾸미고, 카드 문구·마지막 사건·침묵 배지·상세 패널을 본다.
진짜 하네스는 뜨지 않는다 (`_fleet_env`).
"""
import _fleet_env  # noqa: F401
import datetime as dt
import json
import pathlib
import sys
import tempfile
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server  # noqa: E402
from fleet_rt import sessions  # noqa: E402
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
def monitor_server(root):
    with _monitor_fixture.serve(server, root) as (_, base):
        yield base


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
        badge = lambda rid: page.locator("#runs-table-wrap tbody tr", has_text=rid).first.locator(".badge").first  # noqa: E731
        checks.ok("실패한 실행은 '실패' (차단색), 중단은 '중단', 감독이 사라진 것은 '사라짐'",
                  [badge(r).inner_text().strip() for r in ("T-4-S2-a1-110000", "T-5-S2-a1-110000", "T-6-S2-a1-110000")] == ["실패", "중단", "사라짐"]
                  and all("blocked" in (badge(r).get_attribute("class") or "") for r in ("T-4-S2-a1-110000", "T-5-S2-a1-110000")),
                  [badge(r).inner_text() for r in ("T-4-S2-a1-110000", "T-5-S2-a1-110000", "T-6-S2-a1-110000")])
        checks.ok("실행 중인 것은 '실행 중'", badge("T-1-S2-a1-110000").inner_text().strip() == "실행 중", badge("T-1-S2-a1-110000").inner_text())
        checks.ok("함대 탭의 숫자는 작업자만 센다 (실행 중 관리자 1 + 작업자 1 -> 1)",
                  page.locator("#tab-count-fleet").inner_text().strip() == "1", page.locator("#tab-count-fleet").inner_text())
        page.locator(".manager-detail-btn").click()
        page.wait_for_selector("#detail-body .mgr-list", timeout=5000)
        body = page.locator("#detail-body").inner_text()
        checks.ok("관리자 상세: '마지막 사건' 이라는 낱말 (활동 아님)", "마지막 사건" in body and "마지막 활동" not in body, body[:200])
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
    mk(root, "T-4-S2-a1-110000", "worker", end={"state": "failed", "rc": 1, "ended": dt.datetime.now().isoformat(timespec="seconds"),
                                                "fail_kind": "work", "why": "x"}, report="BLOCKED")
    mk(root, "T-5-S2-a1-110000", "worker", end={"state": "killed", "rc": None, "ended": dt.datetime.now().isoformat(timespec="seconds"),
                                                "fail_kind": None, "why": "cancel"})
    mk(root, "T-6-S2-a1-110000", "worker")          # 끝 기록 없고 감독 사라짐 -> lost
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
        finally:
            browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
