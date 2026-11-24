#!/usr/bin/env python3
"""모니터 프로젝트 카드의 '관리 방식' 단추를 브라우저에서 잽니다 - 현재 표시, 고르면 POST 본문, 360px 넘침.

/api/state 의 projects 와 POST /api/project/mode 를 가로챈다 (계약: projects[].mode = {key,label,stamped}).
"""
import _fleet_env  # noqa: F401
import json
import pathlib
import sys
import tempfile
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_monitor_manager import Checks, monitor_server  # noqa: E402
from browser_monitor_deploy import proj  # noqa: E402

LABEL = {"speed": "속도 우선", "balance": "균형", "quality": "품질 우선"}


def open_page(browser, base, box, width=1280, reply=None):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors, posts = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def state_route(route):
        r = route.fetch()
        d = r.json()
        d["projects"] = box["projects"]
        route.fulfill(response=r, body=json.dumps(d), content_type="application/json")

    def post_route(route):
        body = json.loads(route.request.post_data or "{}")
        posts.append(body)
        if reply is not None:
            return route.fulfill(status=reply[0], content_type="application/json", body=json.dumps(reply[1]))
        box["projects"][0]["mode"] = {"key": body["mode"], "label": LABEL[body["mode"]], "stamped": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "project": body["project"], "mode": body["mode"]}))
    page.route("**/api/state*", state_route)
    page.route("**/api/project/mode", post_route)
    page.goto(base + "/", wait_until="load")
    page.click("#tab-projects")
    page.wait_for_selector(".proj-mode")
    return page, posts, errors, ctx


def current(page):
    return page.locator(".proj-mode-btn.is-current").all_inner_texts()


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="projmode-browser-"))
    (root / ".aimem").mkdir()
    checks = Checks()
    with monitor_server(root) as base, sync_playwright() as pw:
        browser = pw.chromium.launch()

        p = proj("VoxLog")
        p["mode"] = {"key": "balance", "label": "균형", "stamped": False}
        box = {"projects": [p]}
        page, posts, errs, ctx = open_page(browser, base, box)
        checks.ok("세 가지가 보인다", page.locator(".proj-mode-btn").all_inner_texts() == ["속도 우선", "균형 · 기본", "품질 우선"],
                  page.locator(".proj-mode-btn").all_inner_texts())
        checks.ok("찍지 않은 프로젝트는 균형(기본)이 현재", current(page) == ["균형 · 기본"], current(page))
        page.locator(".proj-mode-btn[data-mode=quality]").click()
        page.wait_for_selector(".proj-mode-btn.is-current[data-mode=quality]", timeout=8000)
        checks.ok("고른 키가 그대로 POST 된다", posts == [{"project": "VoxLog", "mode": "quality"}], posts)
        checks.ok("다시 그려 현재가 바뀐다", current(page) == ["품질 우선"], current(page))
        checks.ok("페이지 오류 없음", not errs, errs)
        ctx.close()

        p = proj("VoxLog")
        p["mode"] = {"key": "speed", "label": "속도 우선", "stamped": True}
        page, posts, errs, ctx = open_page(browser, base, {"projects": [p]}, reply=(409, {"ok": False, "error": "프로젝트 폴더가 없습니다"}))
        page.locator(".proj-mode-btn[data-mode=quality]").click()
        page.wait_for_selector(".proj-mode-msg:not(:empty)")
        checks.ok("거절되면 까닭을 보이고 단추를 살려 둔다", "폴더가 없습니다" in page.locator(".proj-mode-msg").inner_text()
                  and page.locator(".proj-mode-btn[data-mode=balance]").is_enabled())
        ctx.close()

        for w in (320, 360):
            p = proj("VoxLog-아주-긴-프로젝트-이름-시험")
            p["mode"] = {"key": "balance", "label": "균형", "stamped": False}
            page, posts, errs, ctx = open_page(browser, base, {"projects": [p]}, width=w)
            sw = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
            checks.ok(f"{w}px 가로 넘침 없음", sw[0] <= sw[1], sw)
            ctx.close()
        browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
