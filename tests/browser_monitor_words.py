#!/usr/bin/env python3
"""모니터의 낱말과 가벼운 조작을 브라우저에서 잽니다 - 상태 낱말 한 벌, 엔진이 알려 주는 값, 되묻기 줄이기.

/api/state 를 가로채 꾸민 함대 상태·보드·프로젝트를 넣고, POST 는 가로채 본문을 본다. 진짜 함대는 건드리지 않는다.
"""
import _fleet_env  # noqa: F401
import datetime
import json
import pathlib
import re
import sys
import tempfile
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_monitor_manager import Checks, monitor_server  # noqa: E402


def kst(minutes_ago=0):
    t = datetime.datetime.now(ZoneInfo("Asia/Seoul")).replace(tzinfo=None) - datetime.timedelta(minutes=minutes_ago)
    return t.isoformat(timespec="seconds")


def fleet(mode="paused", label="일시 중지", idle=False, chain=None, prepare=None, manager=None, can_run=True):
    ch = {"on": False, "all": False, "fleet": True, "projects": [], "label": "함대", "max_rounds": 3,
          "limits": {"default": 4, "max": 8, "hard": 25}}
    ch.update(chain or {})
    return {"mode": mode, "label": label, "idle": idle, "default": False, "running_runs": 0, "graphs": [],
            "can": {"prepare": True, "run": can_run, "pause": False, "stop": False, "round": True},
            "brief": {"round": 5, "file": "x.md", "standard": True, "workspace": "rounds/R5"},
            "manager": manager, "chain": ch, "prepare": prepare,
            "policy": {"current": None, "default": "cost", "chain": None,
                       "choices": [{"key": "cost", "label": "무료 중심", "desc": "a"}, {"key": "quality", "label": "품질 중심", "desc": "b"}]}}


def open_page(browser, base, fl, *, tweak=None, routes=None, width=1280, tab=None):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    posts, dialogs, errors = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

    def state_route(route):
        r = route.fetch()
        d = r.json()
        d["fleet"] = fl
        if tweak:
            tweak(d)
        route.fulfill(response=r, body=json.dumps(d), content_type="application/json")

    def post_route(route):
        posts.append((route.request.url, json.loads(route.request.post_data or "{}")))
        key = next((k for k in (routes or {}) if route.request.url.endswith(k)), None)
        code, body = (routes or {}).get(key, (200, {"ok": True}))
        if isinstance(body, list):                       # 호출 순서대로 다른 답
            body = body[min(len([1 for u, _ in posts if u.endswith(key)]) - 1, len(body) - 1)]
            code = 200 if body.get("ok") else 409
        route.fulfill(status=code, content_type="application/json", body=json.dumps(body))
    page.route("**/api/state*", state_route)
    page.route("**/api/fleet/*", post_route)
    page.route("**/api/slots/**", post_route)
    page.goto(base + "/", wait_until="load")
    if tab:
        page.click(tab)
    page.wait_for_selector("#fleet-control .fc-buttons", state="attached", timeout=8000)
    page.wait_for_timeout(300)
    page.posts, page.dialogs, page.errors = posts, dialogs, errors
    return page, ctx


def run(browser, base, checks):
    # ---- 함대: '실행' 인데 도는 것이 없으면 '실행 (대기)'
    page, ctx = open_page(browser, base, fleet(mode="running", label="실행", idle=True, can_run=False))
    pill = page.locator("#fleet-mode-pill").inner_text().strip()
    checks.ok("함대 알약: 실행인데 도는 것이 없으면 '함대: 실행 (대기)'", pill == "함대: 실행 (대기)", pill)
    ctx.close()

    # ---- 재개 결과 문구, 되묻기 없음
    page, ctx = open_page(browser, base, fleet(), routes={"/run": (200, {"ok": True, "note": "n"})})
    page.locator("#fleet-control .fc-buttons button", has_text="재개").click()
    page.wait_for_selector(".fc-msg", timeout=5000)
    msg = page.locator(".fc-msg").inner_text().strip()
    checks.ok("재개를 누른 결과 문구는 '재개 …' (실행 아님)", msg.startswith("재개"), msg)
    ctx.close()

    # ---- 이어 달리기: 엔진 상한, 짧은 안내, 프로젝트 꼬리표·꺼짐 안내 없음, 확인창 없음
    def with_projects(d):
        d["projects"] = [{"name": "알파", "path": "projects/알파/", "exists": True, "percent": 0, "basis": "requests",
                          "goals": None, "request_percent": None, "requests": {"total": 1, "done": 0, "new": 0, "active": 2},
                          "rounds": [], "round_count": 0, "last_round": None, "last_round_at": None, "updated": None,
                          "summary": None, "app": None}]
        d["board"] = [{"id": "T-1", "task": "a", "slot": "S1", "status": "REVIEW", "handoff": "-", "artifact": ""},
                      {"id": "T-2", "task": "b", "slot": "S1", "status": "BLOCKED", "handoff": "-", "artifact": ""}]
    page, ctx = open_page(browser, base, fleet(), tweak=with_projects, routes={"/chain": (200, {"ok": True})})
    chain = page.locator("#fleet-chain")
    num = chain.locator(".fleet-chain-max")
    checks.ok("상한 입력의 기본값·최대는 엔진이 알려 준 값 (4, 8)", num.input_value() == "4" and num.get_attribute("max") == "8",
              f"{num.input_value()} / {num.get_attribute('max')}")
    ctext = chain.inner_text()
    checks.ok("프로젝트 체크박스에 '프로젝트' 꼬리표가 없고 꺼짐 안내 문장도 없다",
              chain.locator(".fleet-chain-kind").count() == 0 and "꺼져 있습니다" not in ctext, ctext[:160])
    chain.locator(".fleet-chain-all").click()
    num.fill("9")
    chain.locator(".fleet-chain-on").click()
    page.wait_for_timeout(300)
    checks.ok("상한이 엔진 최대(8)를 넘으면 보내지 않고 이유를 보인다", not page.posts and "1~8" in chain.inner_text(), chain.inner_text()[-80:])
    num.fill("4")
    chain.locator(".fleet-chain-on").click()
    page.wait_for_timeout(400)
    cp = [b for u, b in page.posts if u.endswith("/chain")]
    checks.ok("이어 달리기를 켤 때 확인창 없이 바로 보낸다", bool(cp) and cp[0].get("max_rounds") == 4 and not page.dialogs, f"{cp} {page.dialogs}")
    # 보드·프로젝트 낱말
    page.click("#tab-board")
    page.wait_for_selector("#board-section tbody tr", timeout=8000)
    words = page.locator("#board-section tbody tr .badge").all_inner_texts()
    checks.ok("보드: REVIEW 는 '관리자 확인 대기', BLOCKED 는 '막힘·실패'", "관리자 확인 대기" in words and "막힘·실패" in words, words)
    page.click("#tab-projects")
    page.wait_for_selector("#projects-list .proj-item", timeout=8000)
    meta = page.locator("#projects-list .proj-item .proj-sub").first.inner_text()
    checks.ok("프로젝트 카드: 처리 중인 요청 수는 '처리 중 N'", "처리 중 2" in meta and "진행 중" not in meta, meta)
    ctx.close()

    # ---- 끝난 이유 블록: 제목 한 줄 + 다음 할 일 한 줄, 사람이 끈 까닭은 한 번만
    def stop(kind, why, rnd=3):
        return {"on": False, "stopped_kind": kind, "stopped_why": why, "stopped_round": rnd, "stopped_at": kst(5), "total_rounds": 3, "cycles": 1}
    page, ctx = open_page(browser, base, fleet(chain=stop("safety", "엔진이 적은 까닭")))
    blk = page.locator(".fleet-chain-stop")
    checks.ok("멈춘 까닭: 제목 + 다음 할 일 한 줄이고 안전 상한은 엔진 값(25)",
              blk.locator(".fleet-chain-stop-head").count() == 1 and blk.locator(".fleet-chain-stop-next").count() == 1
              and blk.locator(".fleet-chain-stop-body").count() == 0 and "25" in blk.inner_text(), blk.inner_text())
    ctx.close()
    page, ctx = open_page(browser, base, fleet(chain=stop("off", "태석 이(가) 껐습니다")))
    blk = page.locator(".fleet-chain-stop").inner_text()
    checks.ok("사람이 끈 까닭은 한 번만 적힌다", blk.count("껐습니다") == 1, blk)
    ctx.close()

    # ---- 준비 점검 한 줄
    prep = {"at": kst(46), "ok": True, "checks": [{"name": "a", "ok": True, "required": True, "detail": ""}]}
    page, ctx = open_page(browser, base, fleet(prepare=prep))
    sm = page.locator("#fleet-control details summary").first.inner_text().strip()
    checks.ok("준비 점검 줄: '준비 점검 HH:MM (46분 전) - 통과'", re.match(r"^준비 점검 \d\d:\d\d \(46분 전\) - 통과$", sm) is not None, sm)
    ctx.close()

    # ---- 유료 관리자 (모델은 엔진이 알려 줄 때만)
    mg = {"round": 5, "label": "R5 관리자", "state": "running", "model": "opus", "workspace": "rounds/R5", "last_event_at": kst(0)}
    page, ctx = open_page(browser, base, fleet(mode="running", label="실행", manager=mg, can_run=False))
    t = page.locator("#fleet-control .btn-primary").first.get_attribute("title") or ""
    checks.ok("라운드 실행 설명: '유료 관리자(opus)' (모델은 엔진 값)", "유료 관리자(opus)" in t and "Opus" not in t, t)
    ctx.close()

    # ---- 슬롯 삭제: 확인은 한 번, 엔진이 거절하면 그 말 + '강제로 지움' 단추
    def with_slot(d):
        d["slots"] = [{"slot": "S1", "harness": "claude", "role": "r", "note": "", "model": "opus", "model_source": "", "origin": "owner", "round": None}]
    page, ctx = open_page(browser, base, fleet(), tweak=with_slot, routes={"/remove": (409, [
        {"ok": False, "error": "S1 에 끝나지 않은 태스크 T-9 가 있습니다"}, {"ok": True}])})
    page.locator("#slots-table-wrap tbody tr").first.click()
    page.wait_for_selector(".slot-form .btn-danger", timeout=5000)
    page.locator(".slot-form .btn-danger").first.click()
    page.wait_for_selector(".slot-force", timeout=5000)
    shown = page.locator(".slot-form .form-msg, .slot-form .slot-msg, .slot-form .hint").all_inner_texts()
    page.locator(".slot-force").click()
    page.wait_for_timeout(500)
    removes = [b for u, b in page.posts if u.endswith("/remove")]
    checks.ok("슬롯 삭제: 확인창 한 번, 거절되면 '강제로 지움' 단추 (확인창 없이 force 로 다시 보냄)",
              len(page.dialogs) == 1 and removes == [{}, {"force": True}], f"{page.dialogs} {removes} {shown}")
    ctx.close()


def main():
    checks = Checks()
    root = pathlib.Path(tempfile.mkdtemp(prefix="words-browser-"))
    (root / ".aimem").mkdir()
    with monitor_server(root) as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            run(browser, base, checks)
        finally:
            browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
