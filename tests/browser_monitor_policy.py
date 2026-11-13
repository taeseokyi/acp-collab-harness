#!/usr/bin/env python3
"""모니터의 운영 방식(무료 중심/품질 중심/빠른 구현) 화면을 브라우저에서 잽니다. 두 칸('지금 R<N>'·'다음 라운드')이고,
칸의 값은 그 칸의 지금 상태에 고정이다 - 칸을 눌러 편 목록에서 고르면 그 칸의 것을 바꾸는 동작이 나간다.

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


def fleet(policy=True, running=None, chain_on=False, switch=False):
    f = {"mode": "running" if running else "ready", "label": "실행" if running else "준비",
         "can": {"prepare": True, "run": False, "pause": False, "stop": False, "round": not running},
         "idle": not running, "brief": {"round": 26, "file": "x.md", "standard": True, "workspace": "rounds/R26"},
         "chain": {"on": chain_on, "all": False, "fleet": True, "projects": [], "label": "함대", "max_rounds": 3,
                   "limits": {"default": 3, "max": 10, "hard": 30}},
         }
    if running:
        f["manager"] = {"round": 26, "state": "running", "label": "R26 관리자", "workspace": "rounds/R26", "policy": running}
    if switch:                       # 서버가 '지금 바꾸기' 를 안다 + 미완 그래프 하나
        f["can"]["switch"] = True
        f["graphs"] = [{"id": "G-060", "runner": True, "counts": {"todo": 3}}]
    if policy:
        f["policy"] = {"current": running, "default": "cost", "chain": "quality" if chain_on else None, "choices": CHOICES}
    return f


def open_page(browser, base, fl, width=1280, new_requests=1, accept=True):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors, posts, dialogs = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept() if accept else d.dismiss()))

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
    page.route("**/api/fleet/switch", post_route)
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
        ROW = '#fleet-control .fc-policy-row[data-row="%s"]'
        cur = lambda page, row: page.locator(ROW % row + " .fc-policy-cur").inner_text().rstrip(" ▾▴")  # noqa: E731

        def pick(page, row, label):
            page.locator(ROW % row + " .fc-policy-cur").click()
            page.locator(ROW % row + " .fc-policy-item", has_text=label).click()

        # 도는 라운드 없음 · 이어 달리기 꺼짐: '다음 라운드' 한 칸, 고른 것은 이 화면이 기억한다
        page, posts, errs, ctx = open_page(browser, base, fleet())
        nxt = page.locator(ROW % "next")
        checks.ok("도는 라운드가 없으면 '다음 라운드' 칸만 있다",
                  page.locator("#fleet-control .fc-policy-row").count() == 1 and nxt.locator(".fc-policy-lab").inner_text() == "다음 라운드")
        checks.ok("칸에 기본값(무료 중심)이 적혀 있고 그 방식의 설명이 옆에 보인다",
                  cur(page, "next") == "무료 중심" and "무료 모델만" in nxt.locator(".fc-policy-desc").inner_text())
        checks.ok("목록은 누르기 전에는 접혀 있다", page.locator(".fc-policy-menu").count() == 0)
        nxt.locator(".fc-policy-cur").click()
        items = nxt.locator(".fc-policy-item")
        checks.ok("칸을 누르면 선택지 3개가 설명과 함께 펴진다",
                  items.count() == 3 and "병렬" in items.nth(2).inner_text() and nxt.locator(".fc-policy-cur").get_attribute("aria-expanded") == "true",
                  items.all_inner_texts())
        checks.ok("지금 값에 ✓ 표시가 있다", "무료 중심 ✓ 다음 방식" in items.nth(0).inner_text() and items.nth(0).get_attribute("aria-selected") == "true")
        checks.ok("목록 맨 위에 고르면 어떻게 되는지 적혀 있다",
                  "고르면 '라운드 실행' 이나 이어 달리기를 켤 때 그 방식으로 띄웁니다 (이 화면에서만 기억합니다)" in nxt.locator(".fc-policy-how").inner_text())
        page.wait_for_timeout(300)
        checks.ok("펴면 초점이 지금 값에 가 있고 화살표로 옮긴다",
                  page.evaluate("document.activeElement.dataset.key") == "cost"
                  and (page.keyboard.press("ArrowDown") or page.evaluate("document.activeElement.dataset.key")) == "quality")
        page.wait_for_timeout(6000)   # 5초 재렌더
        checks.ok("5초 재렌더 뒤에도 목록이 펴져 있고 초점이 남는다",
                  items.count() == 3 and page.evaluate("document.activeElement.dataset.key") == "quality")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        checks.ok("Esc 로 닫히고 초점이 칸으로 돌아간다, 값은 그대로",
                  page.locator(".fc-policy-menu").count() == 0 and cur(page, "next") == "무료 중심"
                  and page.evaluate("document.activeElement.className") == "fc-policy-cur")
        nxt.locator(".fc-policy-cur").click()
        page.locator("#fleet-control .fleet-head, #fleet-control").first.click(position={"x": 5, "y": 5})
        checks.ok("목록 밖을 누르면 닫힌다", page.locator(".fc-policy-menu").count() == 0)
        pick(page, "next", "빠른 구현")
        checks.ok("목록에서 고르면 칸의 값과 설명이 바뀌고 목록이 닫힌다",
                  cur(page, "next") == "빠른 구현" and "병렬" in nxt.locator(".fc-policy-desc").inner_text() and page.locator(".fc-policy-menu").count() == 0)
        checks.ok("고르기만 해서는 아무것도 보내지 않는다", not posts, posts)
        page.wait_for_timeout(6000)
        checks.ok("5초 재렌더 뒤에도 고른 값 유지", cur(page, "next") == "빠른 구현")
        page.locator("#fleet-control .btn-primary").click()
        page.wait_for_timeout(500)
        rp = [b for u, b in posts if u.endswith("/round")]
        checks.ok("라운드 POST 본문에 policy: speed", bool(rp) and rp[0].get("policy") == "speed", rp)
        checks.ok("라운드 실행에 확인창이 없다 (할 일이 있을 때)", not page.dialogs, page.dialogs)
        chain = page.locator("#fleet-chain")
        checks.ok("이어 달리기 폼에는 선택이 없고 고른 방식을 글로만 보인다",
                  chain.locator(".fc-policy").count() == 0 and "운영 방식: 빠른 구현" in chain.inner_text(), chain.inner_text()[-120:])
        pick(page, "next", "품질 중심")
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

        # 라운드 도는 중 · 이어 달리기 켜짐: 두 칸. 값은 서버 상태(지금 = 빠른 구현, 다음 = 이어 달리기의 품질 중심)에 고정
        page, posts, errs, ctx = open_page(browser, base, fleet(running="speed", chain_on=True, switch=True))
        page.wait_for_selector("#manager-card .manager-policy", timeout=8000)
        checks.ok("관리자 카드에 운영 방식 칩", page.locator("#manager-card .manager-policy").inner_text() == "빠른 구현")
        checks.ok("이어 달리기 켜짐 줄에 운영 방식", "품질 중심" in page.locator("#fleet-chain .fleet-chain-what").inner_text())
        labs = page.locator("#fleet-control .fc-policy-lab").all_inner_texts()
        checks.ok("'지금 R26' 과 '다음 라운드' 두 칸이 이 순서로 있다", labs == ["지금 R26", "다음 라운드"], labs)
        checks.ok("지금 칸은 도는 방식, 다음 칸은 이어 달리기의 방식이다 (고르지 않아도)",
                  cur(page, "now") == "빠른 구현" and cur(page, "next") == "품질 중심", (cur(page, "now"), cur(page, "next")))
        txt = page.locator("#fleet-control .fc-hint-now").inner_text()
        checks.ok("아래 '지금 R26 실행 중' 문구는 방식을 또 적지 않는다", "R26 실행 중" in txt and "빠른 구현" not in txt, txt)
        page.locator(ROW % "next" + " .fc-policy-cur").click()
        checks.ok("한 번에 한 칸의 목록만 펴진다 (다음 칸)", page.locator(".fc-policy-menu").count() == 1 and page.locator(ROW % "next" + " .fc-policy-menu").count() == 1)
        how = page.locator(ROW % "next" + " .fc-policy-how").inner_text()
        checks.ok("다음 칸 목록의 설명: 다음 라운드부터, 도는 라운드는 그대로",
                  "고르면 이어 달리기가 다음 라운드부터 그 방식으로 띄웁니다. 도는 라운드는 그대로 갑니다" in how, how)
        page.locator(ROW % "next" + " .fc-policy-item", has_text="무료 중심").click()
        page.wait_for_timeout(500)
        sp = [b for u, b in posts if u.endswith("/switch")]
        checks.ok("다음 칸에서 고르면 되묻지 않고 when: next 로 보낸다",
                  not page.dialogs and sp == [{"policy": "cost", "when": "next"}], (page.dialogs, posts))
        checks.ok("서버 상태가 안 바뀌면 칸의 값은 그대로다 (고른 것만으로 바뀌지 않는다)",
                  cur(page, "now") == "빠른 구현" and cur(page, "next") == "품질 중심")
        posts.clear()
        page.locator(ROW % "now" + " .fc-policy-cur").click()
        how = page.locator(ROW % "now" + " .fc-policy-how").inner_text()
        checks.ok("지금 칸 목록의 설명: 멈추고 다시 띄움·그래프 버림·확인을 받음",
                  "고르면 R26 을 멈추고 그 방식으로 다시 띄웁니다. 그래프는 버리고 새로 짭니다 - 고른 뒤 한 번 더 확인을 받습니다" in how, how)
        page.locator(ROW % "now" + " .fc-policy-item", has_text="빠른 구현").click()
        checks.ok("지금 값을 다시 고르면 닫히기만 한다", page.locator(".fc-policy-menu").count() == 0 and not posts and not page.dialogs)
        pick(page, "now", "무료 중심")
        page.wait_for_timeout(500)
        dl = page.dialogs[-1] if page.dialogs else ""
        checks.ok("지금 칸에서 다른 방식을 고르면 경고와 함께 확인을 받는다 (멈춤·그래프 버림·되돌릴 수 없음)",
                  all(x in dl for x in ("R26 을 지금 멈추고", "빠른 구현 → 무료 중심", "그래프 G-060 를 버립니다", "작업자가 끊깁니다",
                                        "이어 달리기는 새 방식으로", "되돌릴 수 없습니다. 진행할까요?")), dl)
        sp = [b for u, b in posts if u.endswith("/switch")]
        checks.ok("확인하면 switch POST 본문에 policy: cost, when: now, round: 26", sp == [{"policy": "cost", "when": "now", "round": 26}], posts)
        page.wait_for_timeout(6000)
        checks.ok("5초 재렌더 뒤에도 두 칸의 값이 서버 상태 그대로다", cur(page, "now") == "빠른 구현" and cur(page, "next") == "품질 중심")
        checks.ok("페이지 오류 없음 (두 칸)", not errs, errs)
        ctx.close()

        # 라운드 도는 중 · 이어 달리기 꺼짐 (320px): 다음 칸은 이 화면의 선택, 지금 칸은 확인을 받는다 - 취소하면 안 보낸다
        page, posts, errs, ctx = open_page(browser, base, fleet(running="speed", switch=True), width=320, accept=False)
        checks.ok("고른 것이 없으면 다음 칸은 도는 라운드의 방식이다 (기본값이 아니라)", cur(page, "next") == "빠른 구현", cur(page, "next"))
        pick(page, "next", "품질 중심")
        checks.ok("이어 달리기가 꺼져 있으면 다음 칸은 고르는 대로 바뀌고 아무것도 보내지 않는다",
                  cur(page, "next") == "품질 중심" and cur(page, "now") == "빠른 구현" and not posts, posts)
        page.locator(ROW % "now" + " .fc-policy-cur").click()
        sw = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
        checks.ok("320px 에서 목록을 펴도 가로 넘침 없음", sw[0] <= sw[1], sw)
        page.locator(ROW % "now" + " .fc-policy-item", has_text="품질 중심").click()
        page.wait_for_timeout(500)
        checks.ok("확인창에서 취소하면 아무것도 보내지 않고 값도 그대로다",
                  len(page.dialogs) == 1 and not posts and cur(page, "now") == "빠른 구현", (page.dialogs, posts))
        checks.ok("이어 달리기가 꺼져 있으면 확인 글에 이어 달리기 줄이 없다", "이어 달리기" not in page.dialogs[0], page.dialogs)
        ctx.close()

        # 서버가 지금 바꾸기를 모르거나(옛 서버) 누가 바꾸는 중이면 지금 칸은 보이기만 한다
        page, posts, errs, ctx = open_page(browser, base, fleet(running="quality", chain_on=True))
        nowb = page.locator(ROW % "now" + " .fc-policy-cur")
        checks.ok("지금 바꿀 수 없으면 지금 칸은 값만 보이고 눌리지 않는다 (▾ 없음)",
                  nowb.inner_text() == "품질 중심" and nowb.is_disabled())
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
