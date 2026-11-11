#!/usr/bin/env python3
"""T-135 브라우저 실측: 인증을 켠 채로 /app/웹워들/ 미리보기가 뜨는지 6문항을 잰다.

T-134 의 경로 티켓(/app/~<티켓>/<이름>/…) 고침이 진짜인지 인증을 켠 서버에서 확인한다.
뼈대는 tests/browser_monitor_app.py 에서 복사했고, 서버만 require_auth=True 로 띄운다.
"""
import http.server
import pathlib
import sys
import threading
from contextlib import contextmanager
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import server          # noqa: E402


TOKEN = "a" * 64                      # 접근 토큰 (64자 16진수 꼴)


class Checks:
    def __init__(self):
        self.results = []

    def ok(self, goal, cond, detail=""):
        self.results.append((bool(cond), goal, detail))
        return bool(cond)

    def finish(self):
        failures = 0
        for passed, goal, detail in self.results:
            line = f"[{'OK' if passed else 'FAIL'}] {goal}"
            if detail:
                line += f" - {detail}"
            print(line)
            if not passed:
                failures += 1
        print(f"통과 {len(self.results) - failures} / 전체 {len(self.results)}")
        return failures


@contextmanager
def monitor_server():
    """인증 켠 http 모니터를 임시 포트에 띄웁니다."""
    handler = type("H", (server.Handler,), {"root": ROOT, "require_auth": True, "tls": False,
                                             "access_token": TOKEN, "guard": server.LoginGuard(),
                                             "timeout": 5, "log_message": lambda *a, **k: None})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def _step(checks, goal, fn):
    try:
        return fn()
    except Exception as exc:
        checks.ok(goal, False, f"{type(exc).__name__}: {exc}")
        return None


def check_login_blocked(ctx, base, checks):
    """1. 로그인 전에는 막힌다 - 새 컨텍스트는 게임 HTML 을 못 받는다."""
    ctx2 = ctx.browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        resp = ctx2.request.get(base + "/app/웹워들/")
        text = resp.text()
        has_board = 'id="board"' in text or "id='board'" in text
        checks.ok("로그인 전에는 막힌다", resp.status != 200 or not has_board,
                  f"상태={resp.status}, 게임HTML(id=board)={has_board}")
    finally:
        ctx2.close()


def check_login_works(ctx, base, checks):
    """2. 로그인이 된다 - 세션 쿠키가 컨텍스트에 남고 목록이 보인다 (페이지 반환)."""
    r = ctx.request.post(base + "/api/login", data={"token": TOKEN},
                         headers={"Content-Type": "application/json"})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#projects-list .proj-item", timeout=10000)
        n = page.locator("#projects-list .proj-item").count()
        checks.ok("로그인이 된다", r.status == 200 and n >= 1,
                  f"login status={r.status}, 목록 항목 {n}개")
    except Exception:
        page.close()
        raise
    return page


def check_preview_visible(page, base, checks):
    """3. '실행' 을 누르면 미리보기(iframe)가 뜬다."""
    run = page.locator(".proj-run").first
    run.wait_for(state="attached", timeout=10000)
    run.click()
    frame_el = page.locator("iframe.proj-app-frame")
    frame_el.wait_for(state="visible", timeout=10000)
    box = frame_el.bounding_box()
    h = box["height"] if box else 0
    checks.ok("'실행' 을 누르면 미리보기가 보인다", bool(box) and h >= 300,
              f"가시=True, 높이={h}")


def check_inner_drawn(page, base, checks):
    """4. (핵심) 미리보기 안쪽이 진짜로 그려졌다 - 타일 30칸."""
    fl = page.frame_locator("iframe.proj-app-frame")
    tiles = fl.locator("#board .tile")
    tiles.first.wait_for(state="attached", timeout=10000)
    n = tiles.count()
    vis = tiles.first.is_visible()
    checks.ok("안쪽이 진짜로 그려졌다", n == 30 and vis, f"타일 {n}개, 첫 칸 가시={vis}")
    return tiles


def check_css_applied(tiles, checks):
    """5. CSS 도 실제로 입혀졌다 - 첫 칸 테두리 존재."""
    bw = tiles.first.evaluate("el => getComputedStyle(el).borderWidth")
    checks.ok("CSS 가 실제로 입혀졌다", bw != "0px", f"borderWidth={bw!r}")


def check_sandbox_isolation(page, base, checks):
    """6. 그래도 격리는 살아 있다 - 프레임 문서는 불투명 출처."""
    src = page.locator("iframe.proj-app-frame").get_attribute("src")
    target = urljoin(page.url, src) if src else None
    others = [f for f in page.frames if f != page.main_frame]
    frame = next((f for f in others if target and f.url == target), None)
    if frame is None and others:
        frame = others[0]
    if frame is None:
        raise ValueError("iframe 프레임을 찾지 못함")
    origin = frame.evaluate("() => window.origin")
    checks.ok("격리는 살아 있다(불투명 출처)", origin == "null", f"window.origin={origin!r}")


def run_checks(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        _step(checks, "로그인 전에는 막힌다", lambda: check_login_blocked(ctx, base, checks))
        page = _step(checks, "로그인이 된다", lambda: check_login_works(ctx, base, checks))
        _step(checks, "'실행' 을 누르면 미리보기가 보인다",
              lambda: check_preview_visible(page, base, checks))
        tiles = _step(checks, "안쪽이 진짜로 그려졌다",
                       lambda: check_inner_drawn(page, base, checks))
        _step(checks, "CSS 가 실제로 입혀졌다", lambda: check_css_applied(tiles, checks))
        _step(checks, "격리는 살아 있다(불투명 출처)",
              lambda: check_sandbox_isolation(page, base, checks))
    finally:
        ctx.close()


def main():
    checks = Checks()
    try:
        with monitor_server() as base:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    run_checks(browser, base, checks)
                finally:
                    browser.close()
    except Exception as exc:
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
