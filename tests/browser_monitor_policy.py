#!/usr/bin/env python3
"""모니터의 운영 방식(무료 중심/품질 중심/빠른 구현) 화면을 브라우저에서 잽니다. 고르는 곳은 '라운드 실행' 옆 한 곳이고 이어 달리기는 그 값을 따른다.

/api/state 의 fleet 부분만 가로채 바꾼다 (엔진 계약: fleet.policy, fleet.manager.policy).
POST /api/fleet/round · /api/fleet/chain 도 가로채 본문을 본다. 진짜 함대는 건드리지 않는다.
"""
import _fleet_env  # noqa: F401
import json
import pathlib
import sys
import tempfile
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_monitor_manager import Checks, monitor_server, mk, ev  # noqa: E402

CHOICES = [{"key": "cost", "label": "무료 중심", "desc": "작업자는 무료 모델만 씁니다"},
           {"key": "quality", "label": "품질 중심", "desc": "어려운 일에는 유료 모델을 씁니다"},
           {"key": "speed", "label": "빠른 구현", "desc": "병렬로 많이 띄워 빨리 끝냅니다"}]


def fleet(policy=True, running=None, chain_on=False):
    f = {"mode": "running" if running else "ready", "label": "실행" if running else "준비",
         "can": {"prepare": True, "run": False, "pause": False, "stop": False, "round": not running},
         "idle": not running, "brief": {"round": 26, "file": "x.md", "standard": True, "workspace": "rounds/R26"},
         "chain": {"on": chain_on, "all": False, "fleet": True, "projects": [], "label": "함대", "max_rounds": 3,
                   "limits": {"default": 3, "max": 10, "hard": 30}},
         }
    if running:
        f["manager"] = {"round": 26, "state": "running", "label": "R26 관리자", "workspace": "rounds/R26", "policy": running}
    if policy:
        f["policy"] = {"current": running, "default": "cost", "chain": "quality" if chain_on else None, "choices": CHOICES}
    return f


def open_page(browser, base, fl, width=1280, new_requests=1):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors, posts, dialogs = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

    def state_route(route):
        r = route.fetch()
        d = r.json()
        d["fleet"] = fl
        d["requests"] = [{"id": f"Q-{i}", "title": f"할 일 {i}", "status": "NEW", "created": "2026-11-13T00:00:00",
                          "requester": "t", "subtasks": [], "detail": "", "detail_truncated": False, "detail_len": 0,
                          "progress_pct": 0.0, "eta_sec": None, "eta_basis": ""} for i in range(new_requests)]
        route.fulfill(response=r, body=json.dumps(d), content_type="application/json")

    def post_route(route):
        posts.append((route.request.url, json.loads(route.request.post_data or "{}")))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "round": 26, "brief": "x"}))
    page.route("**/api/state*", state_route)
    page.route("**/api/fleet/round", post_route)
    page.route("**/api/fleet/chain", post_route)
    page.goto(base + "/", wait_until="load")
    page.wait_for_selector("#fleet-control .fc-buttons", timeout=8000)
    page.dialogs = dialogs
    return page, posts, errors, ctx


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="policy-browser-"))
    (root / ".aimem").mkdir()
    mk(root, "M-R26-110000", "manager", running=True, events=[(30, ev(type="text", text="작업"))],
       extra_meta={"round": 26, "label": "R26 관리자"})
    checks = Checks()
    with monitor_server(root) as base, sync_playwright() as pw:
        browser = pw.chromium.launch()
        page, posts, errs, ctx = open_page(browser, base, fleet())
        seg = page.locator("#fleet-control .fc-policy-opt")
        checks.ok("운영 방식 선택지 3개가 보인다", seg.count() == 3, seg.all_inner_texts())
        checks.ok("기본값(무료 중심)이 선택돼 있다", page.locator("#fleet-control .fc-policy input:checked").get_attribute("value") == "cost")
        checks.ok("선택한 항목의 설명이 한 줄로 보인다", "무료 모델만" in page.locator("#fleet-control .fc-policy-desc").inner_text())
        checks.ok("각 선택지에 title 설명이 있다", "병렬" in (seg.nth(2).get_attribute("title") or ""))
        page.locator("#fleet-control .fc-policy-opt", has_text="빠른 구현").click()
        checks.ok("고르면 설명이 바뀐다", "병렬" in page.locator("#fleet-control .fc-policy-desc").inner_text())
        page.wait_for_timeout(6000)   # 5초 재렌더 뒤에도 선택이 남는다
        checks.ok("5초 재렌더 뒤에도 선택 유지", page.locator("#fleet-control .fc-policy input:checked").get_attribute("value") == "speed")
        page.locator("#fleet-control .btn-primary").click()
        page.wait_for_timeout(500)
        rp = [b for u, b in posts if u.endswith("/round")]
        checks.ok("라운드 POST 본문에 policy: speed", bool(rp) and rp[0].get("policy") == "speed", rp)
        checks.ok("라운드 실행에 확인창이 없다 (할 일이 있을 때)", not page.dialogs, page.dialogs)
        chain = page.locator("#fleet-chain")
        checks.ok("이어 달리기 폼에는 선택이 없고 고른 방식을 글로만 보인다",
                  chain.locator(".fc-policy").count() == 0 and "운영 방식: 빠른 구현" in chain.inner_text(), chain.inner_text()[-120:])
        page.locator("#fleet-control .fc-policy-opt", has_text="품질 중심").click()
        checks.ok("고르는 곳을 바꾸면 이어 달리기 글도 따라 바뀐다", "운영 방식: 품질 중심" in chain.inner_text())
        chain.locator(".fleet-chain-opt.is-fleet input").check()
        chain.locator(".fleet-chain-on").click()          # 확인창 없이 바로 보낸다
        page.wait_for_timeout(500)
        cp = [b for u, b in posts if u.endswith("/chain")]
        checks.ok("이어 달리기 POST 본문에 policy: quality", bool(cp) and cp[0].get("policy") == "quality" and cp[0].get("on") is True, cp)
        checks.ok("이어 달리기를 켤 때 확인창이 없다", not page.dialogs, page.dialogs)
        checks.ok("페이지 오류 없음", not errs, errs)
        ctx.close()

        page, posts, errs, ctx = open_page(browser, base, fleet(), new_requests=0)
        page.locator("#fleet-control .btn-primary").click()
        page.wait_for_timeout(500)
        checks.ok("새 요청이 없을 때만 라운드 실행이 한 번 되묻는다",
                  len(page.dialogs) == 1 and "할 일이 없습니다" in page.dialogs[0], page.dialogs)
        ctx.close()

        page, posts, errs, ctx = open_page(browser, base, fleet(running="quality", chain_on=True))
        page.wait_for_selector("#manager-card .manager-policy", timeout=8000)
        checks.ok("관리자 카드에 운영 방식 칩", page.locator("#manager-card .manager-policy").inner_text() == "품질 중심")
        txt = page.locator("#fleet-control").inner_text()
        checks.ok("함대 카드 문구에 운영 방식 (R26 실행 중 · 품질 중심)", "R26 실행 중 · 품질 중심" in txt, txt[:200])
        checks.ok("이어 달리기 켜짐 줄에 운영 방식", "품질 중심" in page.locator("#fleet-chain .fleet-chain-what").inner_text())
        ctx.close()

        for w in (320, 360, 430):
            for fl in (fleet(), fleet(running="speed", chain_on=True)):
                page, posts, errs, ctx = open_page(browser, base, fl, width=w)
                sw = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
                checks.ok(f"{w}px 가로 넘침 없음 (이어 달리기 {'켬' if fl['chain']['on'] else '끔'})", sw[0] <= sw[1], sw)
                ctx.close()

        page, posts, errs, ctx = open_page(browser, base, fleet(policy=False, running="quality"))
        page.wait_for_timeout(500)
        checks.ok("policy 키가 없으면 운영 방식 UI 가 없다", page.locator(".fc-policy, .manager-policy").count() == 0)
        checks.ok("policy 키가 없으면 라운드 문구에 방식이 안 붙는다", "품질 중심" not in page.locator("#fleet-control").inner_text())
        ctx.close()
        browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
