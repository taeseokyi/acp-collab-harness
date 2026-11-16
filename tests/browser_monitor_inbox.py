#!/usr/bin/env python3
"""모니터의 '관리자에게 말 남기기' 를 브라우저에서 잽니다 - 관리자 카드의 한 줄, 패널의 입력·목록, POST 본문.

/api/state 의 fleet 부분만 가로채 바꾼다 (엔진 계약: fleet.inbox, fleet.can.tell).
POST /api/fleet/tell 도 가로채 본문을 본다. 진짜 함대는 건드리지 않는다.
"""
import _fleet_env  # noqa: F401
import json
import pathlib
import sys
import tempfile
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_monitor_manager import Checks, monitor_server, mk, ev  # noqa: E402

OLD = {"at": "2026-11-16T14:06:22", "by": "웹(태석)", "text": "요청 본문을 고쳤습니다.\n\n- 위치정보도 같이 올리기"}


def fleet(tell=True, items=()):
    f = {"mode": "running", "label": "실행", "idle": not tell,
         "can": {"prepare": False, "run": False, "pause": tell, "stop": tell, "round": False, "tell": tell},
         "brief": {"round": 26, "file": "x.md", "standard": True, "workspace": "rounds/R26"},
         "chain": {"on": False, "all": False, "fleet": True, "projects": [], "label": "함대", "max_rounds": 3,
                   "limits": {"default": 3, "max": 10, "hard": 30}},
         "manager": {"round": 26, "state": "running" if tell else "done", "label": "R26 관리자", "workspace": "rounds/R26"},
         "inbox": {"round": 26, "items": list(items)} if tell else None}
    return f


def req(rid, status="NEW"):
    return {"id": rid, "title": "할 일 " + rid, "status": status, "created": "2026-11-16T13:58:00", "requester": "t",
            "subtasks": [], "detail": "", "detail_truncated": False, "detail_len": 0, "progress_pct": 0.0,
            "eta_sec": None, "eta_basis": ""}


def open_page(browser, base, box, width=1280, reply=None):
    """box["fleet"] 를 바꾸면 다음 /api/state 부터 그 값이 나간다."""
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors, posts = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def state_route(route):
        r = route.fetch()
        d = r.json()
        d["fleet"] = box["fleet"]
        if "requests" in box:
            d["requests"] = box["requests"]
        route.fulfill(response=r, body=json.dumps(d), content_type="application/json")

    def post_route(route):
        body = json.loads(route.request.post_data or "{}")
        posts.append(body)
        if reply is None:
            box["fleet"] = fleet(items=box["fleet"]["inbox"]["items"]
                                 + [{"at": "2026-11-16T14:20:00", "by": "웹(검사)", "text": body.get("message")}])
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "round": 26}))
        else:
            route.fulfill(status=reply[0], content_type="application/json", body=json.dumps(reply[1]))
    page.route("**/api/state*", state_route)
    page.route("**/api/fleet/tell", post_route)
    page.goto(base + "/", wait_until="load")
    page.wait_for_selector("#manager-card .manager-head", timeout=8000)
    return page, posts, errors, ctx


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="inbox-browser-"))
    (root / ".aimem").mkdir()
    mk(root, "M-R26-110000", "manager", running=True, events=[(30, ev(type="text", text="작업"))],
       extra_meta={"round": 26, "label": "R26 관리자"})
    checks = Checks()
    with monitor_server(root) as base, sync_playwright() as pw:
        browser = pw.chromium.launch()

        # 관리자가 도는데 남긴 말이 없다 → 줄과 단추, 패널에서 남기기
        page, posts, errs, ctx = open_page(browser, base, {"fleet": fleet()})
        row = page.locator("#manager-card .manager-inbox")
        checks.ok("관리자가 돌면 카드에 남긴 말 줄과 '말 남기기' 단추가 있다",
                  row.count() == 1 and "남긴 말 없음" in row.inner_text() and row.locator("button").inner_text() == "말 남기기")
        row.locator("button").click()
        page.wait_for_selector(".inbox-panel .inbox-input")
        checks.ok("패널 제목에 라운드가 붙는다", "R26" in page.locator("#detail-label").inner_text())
        checks.ok("남긴 말이 없으면 없다고 적는다", page.locator(".inbox-empty").count() == 1)
        page.locator(".inbox-send").click()
        checks.ok("빈 말은 보내지 않는다", not posts and "적으십시오" in page.locator(".inbox-msg").inner_text())
        page.locator(".inbox-input").fill("  위치정보도 같이 올려 주십시오  ")
        page.wait_for_timeout(5600)          # 5초 재렌더가 지나도 적던 글이 남아야 한다
        checks.ok("5초 재렌더 뒤에도 적던 글이 남는다", "위치정보" in page.locator(".inbox-input").input_value())
        page.locator(".inbox-send").click()
        page.wait_for_selector(".inbox-item", timeout=8000)
        checks.ok("남기면 다듬은 글이 message 로 나간다", posts == [{"message": "위치정보도 같이 올려 주십시오"}], posts)
        checks.ok("남긴 뒤 패널에 그 말과 알림이 보이고 입력란은 비었다",
                  "위치정보도 같이" in page.locator(".inbox-item").first.inner_text()
                  and "남겼습니다" in page.locator(".inbox-msg").inner_text()
                  and page.locator(".inbox-input").input_value() == "")
        checks.ok("같은 패널을 다시 그려도 '← 이전' 이 생기지 않는다",
                  page.locator("#detail-back").count() == 0 or page.locator("#detail-back").is_hidden())
        page.locator("#detail-close").click()
        checks.ok("카드 줄이 건수와 최근 말로 바뀐다", "남긴 말 1건" in row.inner_text() and "위치정보" in row.inner_text(), row.inner_text())
        checks.ok("페이지 오류 없음", not errs, errs)
        ctx.close()

        # 이미 남긴 말이 있다 → 최근 것이 위, 줄바꿈·목록이 살아 있다. 서버가 거절하면 글을 지우지 않는다
        two = [OLD, {"at": "2026-11-16T14:30:00", "by": "클로드 코드", "text": "<b>굵게</b> 는 글자 그대로"}]
        page, posts, errs, ctx = open_page(browser, base, {"fleet": fleet(items=two)},
                                           reply=(409, {"ok": False, "error": "돌고 있는 라운드가 없습니다"}))
        page.locator("#manager-card .manager-inbox button").click()
        page.wait_for_selector(".inbox-item")
        heads = page.locator(".inbox-item-head").all_inner_texts()
        checks.ok("최근 말이 위에 온다", len(heads) == 2 and "클로드 코드" in heads[0] and "웹(태석)" in heads[1], heads)
        checks.ok("말 속 HTML 은 글자 그대로 보인다", page.locator(".inbox-item b").count() == 0
                  and "<b>굵게</b>" in page.locator(".inbox-item").first.inner_text())
        page.locator(".inbox-input").fill("늦은 말")
        page.locator(".inbox-send").click()
        page.wait_for_timeout(800)
        checks.ok("거절되면 까닭을 보이고 적은 글과 단추를 살려 둔다",
                  "돌고 있는 라운드가 없습니다" in page.locator(".inbox-msg").inner_text()
                  and page.locator(".inbox-input").input_value() == "늦은 말" and page.locator(".inbox-send").is_enabled())
        ctx.close()

        # 관리자가 돌지 않으면 이 기능은 없다
        page, posts, errs, ctx = open_page(browser, base, {"fleet": fleet(tell=False)})
        page.wait_for_timeout(500)
        checks.ok("관리자가 돌지 않으면 남긴 말 줄이 없다", page.locator(".manager-inbox").count() == 0)
        ctx.close()

        # 도는 라운드가 가져간 요청은 '수정' 대신 '말 남기기', 도중에 넣은 요청은 그대로 '수정'
        fl = fleet()
        fl["held"] = {"round": 26, "requests": ["Q-held"]}
        for w in (1280, 360):
            page, posts, errs, ctx = open_page(browser, base, {"fleet": fl, "requests": [req("Q-held"), req("Q-late")]}, width=w)
            page.click("#tab-requests")
            page.wait_for_selector(".req-edit-btn")
            texts = page.locator(".req-edit-btn").all_inner_texts()
            checks.ok(f"{w}px 가져간 요청은 'R26 에 말 남기기', 나머지는 '수정'", sorted(texts) == ["R26 에 말 남기기", "수정"], texts)
            sw = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
            checks.ok(f"{w}px 요청 목록 가로 넘침 없음", sw[0] <= sw[1], sw)
            page.locator(".req-tell-btn").click()
            page.wait_for_selector(".inbox-panel .inbox-input")
            checks.ok(f"{w}px 그 단추가 말 남기기 패널을 연다", "R26" in page.locator("#detail-label").inner_text())
            ctx.close()
        fl = fleet(tell=False)
        page, posts, errs, ctx = open_page(browser, base, {"fleet": fl, "requests": [req("Q-held")]})
        page.click("#tab-requests")
        page.wait_for_selector(".req-edit-btn")
        checks.ok("라운드가 끝나면 다시 '수정' 이다", page.locator(".req-edit-btn").all_inner_texts() == ["수정"])
        ctx.close()

        long = [{"at": "2026-11-16T14:06:22", "by": "웹(태석)", "text": "아주긴말" * 200}]
        for w in (320, 360, 430):
            page, posts, errs, ctx = open_page(browser, base, {"fleet": fleet(items=long)}, width=w)
            sw = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
            checks.ok(f"{w}px 카드 가로 넘침 없음", sw[0] <= sw[1], sw)
            page.locator("#manager-card .manager-inbox button").click()
            page.wait_for_selector(".inbox-item")
            over = page.evaluate("(() => { const p = document.querySelector('#run-detail-panel').getBoundingClientRect();"
                                 " return [...document.querySelectorAll('.inbox-input, .inbox-send, .inbox-item')]"
                                 ".filter((e) => e.getBoundingClientRect().right > p.right + 1).length; })()")
            checks.ok(f"{w}px 패널 안 넘침 없음", over == 0, over)
            ctx.close()
        browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
