#!/usr/bin/env python3
"""모니터 프로젝트 탭의 '배포' 를 브라우저에서 잽니다 - 카드의 단추, 패널의 켜기·내리기·토큰, POST 본문.

/api/state 의 projects 만 가로채 바꾼다 (계약: projects[].deploy, deployable). POST /api/projects/<이름>/deploy 도
가로채 본문을 본다. 진짜 배포는 건드리지 않는다.
"""
import _fleet_env  # noqa: F401
import json
import pathlib
import sys
import tempfile
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from browser_monitor_manager import Checks, monitor_server  # noqa: E402


def proj(name, deploy=None, deployable=True):
    return {"name": name, "path": f"projects/{name}/", "exists": True, "percent": 50.0, "basis": "goals",
            "goals": {"total": 2, "done": 1}, "request_percent": 0.0, "requests": {"total": 1, "done": 0, "new": 0, "active": 1},
            "rounds": [33], "round_count": 1, "last_round": 33, "last_round_at": "2026-11-16T14:00:03", "updated": None,
            "summary": "", "app": {"runnable": True, "url": f"/app/{name}/", "title": name, "root": "web", "entry": "index.html",
                                   "server": "serve.py"} if deployable else None,
            "deploy": deploy, "deployable": deployable}


def dep(on=True, alive=True, auth=True, port=18810):
    return {"name": "VoxLog", "port": port, "on": on, "alive": alive, "auth": auth,
            "started": "2026-11-16T15:30:00" if alive else None}


def open_page(browser, base, box, width=1280, reply=None, accept=True):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    errors, posts, dialogs = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept() if accept else d.dismiss()))

    def state_route(route):
        r = route.fetch()
        d = r.json()
        d["projects"] = box["projects"]
        route.fulfill(response=r, body=json.dumps(d), content_type="application/json")

    def post_route(route):
        body = json.loads(route.request.post_data or "{}")
        posts.append((route.request.url.rsplit("/api/", 1)[1], body))
        if reply is not None:
            return route.fulfill(status=reply[0], content_type="application/json", body=json.dumps(reply[1]))
        if body.get("action") == "on":
            now = dep(auth=body.get("auth", True))
            box["projects"] = [proj("VoxLog", now)]
            out = dict(now, token="tok-NEW" if now["auth"] else None, proxy=box.get("proxy", True),
                       proxy_note=None if box.get("proxy", True) else "윈도우 프록시 폴더가 없습니다")
        elif body.get("action") == "off":
            now = dep(on=False, alive=False)
            box["projects"] = [proj("VoxLog", now)]
            out = dict(now, proxy=True, proxy_note=None)
        else:
            out = dict(dep(), token="tok-SHOWN")
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "deploy": out}))
    page.route("**/api/state*", state_route)
    page.route("**/api/projects/*/deploy", post_route)
    page.goto(base + "/", wait_until="load")
    page.click("#tab-projects")
    page.wait_for_selector(".proj-actions")
    return page, posts, errors, dialogs, ctx


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="deploy-browser-"))
    (root / ".aimem").mkdir()
    checks = Checks()
    with monitor_server(root) as base, sync_playwright() as pw:
        browser = pw.chromium.launch()

        # 배포한 적 없는 앱: '배포…' → 켜기(토큰) → 주소·토큰이 보인다 → 내리기
        box = {"projects": [proj("VoxLog"), proj("웹워들", deployable=False)]}
        page, posts, errs, dialogs, ctx = open_page(browser, base, box)
        btns = page.locator(".proj-deploy").all_inner_texts()
        checks.ok("server 선언이 있는 앱에만 '배포…' 단추가 있다", btns == ["배포…"], btns)
        page.locator(".proj-deploy").click()
        page.wait_for_selector(".deploy-panel")
        checks.ok("처음에는 '내려 있음', 토큰으로 막기가 켜져 있다",
                  "내려 있음" in page.locator(".deploy-state").inner_text() and page.locator(".deploy-auth input").is_checked())
        page.get_by_role("button", name="배포 켜기").click()
        page.wait_for_selector(".deploy-token-val")
        checks.ok("켜면 action on · auth true 가 프로젝트 이름 경로로 나간다",
                  posts == [("projects/VoxLog/deploy", {"action": "on", "auth": True})] and not dialogs, (posts, dialogs))
        host = page.evaluate("location.hostname")
        link = page.locator("a.deploy-url")
        checks.ok("켠 뒤 주소가 모니터와 같은 호스트의 배포 포트(https)로 보이고 새 탭 링크다",
                  link.inner_text() == f"https://{host}:18810/" and link.get_attribute("target") == "_blank", link.inner_text())
        checks.ok("받은 토큰과 '배포 중' 이 보인다", page.locator(".deploy-token-val").inner_text() == "tok-NEW"
                  and "배포 중" in page.locator(".deploy-state").inner_text() and "켰습니다" in page.locator(".deploy-msg").inner_text())
        page.wait_for_timeout(5600)
        checks.ok("5초 재렌더 뒤에도 패널과 토큰이 남는다", page.locator(".deploy-token-val").count() == 1)
        page.get_by_role("button", name="토큰 보기").click()
        page.wait_for_timeout(600)
        checks.ok("'토큰 보기' 는 action token 으로 다시 받아 보인다",
                  posts[-1][1] == {"action": "token"} and page.locator(".deploy-token-val").inner_text() == "tok-SHOWN", posts[-1])
        page.get_by_role("button", name="내리기").click()
        page.wait_for_selector(".deploy-auth")
        checks.ok("내리면 action off, '내려 있음' 이고 주소는 글로만 남는다",
                  posts[-1][1] == {"action": "off"} and "내려 있음" in page.locator(".deploy-state").inner_text()
                  and page.locator("a.deploy-url").count() == 0 and "18810" in page.locator(".deploy-url").inner_text())
        page.locator("#detail-close").click()
        checks.ok("카드 단추가 다시 '배포…' 다", page.locator(".proj-deploy").inner_text() == "배포…")
        checks.ok("페이지 오류 없음", not errs, errs)
        ctx.close()

        # 토큰 없이: 확인창을 거친다. 취소하면 안 나간다
        for accept in (False, True):
            box = {"projects": [proj("VoxLog")], "proxy": False}
            page, posts, errs, dialogs, ctx = open_page(browser, base, box, accept=accept)
            page.locator(".proj-deploy").click()
            page.locator(".deploy-auth input").uncheck()
            page.get_by_role("button", name="배포 켜기").click()
            page.wait_for_timeout(900)
            if accept:
                checks.ok("토큰 없이: 확인 뒤 auth false 로 나가고 토큰 칸은 없다",
                          len(dialogs) == 1 and posts == [("projects/VoxLog/deploy", {"action": "on", "auth": False})]
                          and page.locator(".deploy-token-val").count() == 0
                          and "토큰 없음" in page.locator(".deploy-state").inner_text(), (dialogs, posts))
                checks.ok("프록시에 알리지 못했으면 그 까닭을 덧붙인다", "프록시 폴더" in page.locator(".deploy-msg").inner_text())
                checks.ok("토큰 없는 배포에는 '토큰 보기' 가 없다", page.get_by_role("button", name="토큰 보기").count() == 0)
            else:
                checks.ok("토큰 없이: 확인창에서 취소하면 아무것도 안 나간다", len(dialogs) == 1 and not posts, (dialogs, posts))
            ctx.close()

        # 켜 두었는데 죽어 있다 / 서버가 거절한다
        box = {"projects": [proj("VoxLog", dep(alive=False))]}
        page, posts, errs, dialogs, ctx = open_page(browser, base, box, reply=(502, {"ok": False, "error": "앱 서버가 바로 끝났습니다"}))
        checks.ok("켜 두었는데 죽어 있으면 카드가 '배포 멈춤 !' 이다", page.locator(".proj-deploy").inner_text() == "배포 멈춤 !")
        page.locator(".proj-deploy").click()
        page.get_by_role("button", name="다시 띄우기").click()
        page.wait_for_timeout(700)
        checks.ok("거절되면 까닭을 보이고 단추를 살려 둔다", "앱 서버가 바로 끝났습니다" in page.locator(".deploy-msg").inner_text()
                  and page.get_by_role("button", name="다시 띄우기").is_enabled())
        ctx.close()

        for w in (320, 360, 430):
            box = {"projects": [proj("VoxLog", dep())]}
            page, posts, errs, dialogs, ctx = open_page(browser, base, box, width=w)
            checks.ok(f"{w}px 카드 단추 '배포 중 :18810'", page.locator(".proj-deploy").inner_text() == "배포 중 :18810")
            sw = page.evaluate("[document.documentElement.scrollWidth, innerWidth]")
            checks.ok(f"{w}px 프로젝트 탭 가로 넘침 없음", sw[0] <= sw[1], sw)
            page.locator(".proj-deploy").click()
            page.get_by_role("button", name="토큰 보기").click()
            page.wait_for_selector(".deploy-token-val")
            over = page.evaluate("(() => { const p = document.querySelector('#run-detail-panel').getBoundingClientRect();"
                                 " return [...document.querySelectorAll('.deploy-panel *')]"
                                 ".filter((e) => e.getBoundingClientRect().right > p.right + 1).length; })()")
            checks.ok(f"{w}px 패널 안 넘침 없음", over == 0, over)
            ctx.close()
        browser.close()
    return checks.finish()


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
