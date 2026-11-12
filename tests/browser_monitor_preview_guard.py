#!/usr/bin/env python3
"""T-185 브라우저 실측: 미리보기 보관함이 엉뚱한 쪽의 put 을 무시하는지 잰다."""
import http.server
import json
import pathlib
import sys
import threading
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import server  # noqa: E402


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
    handler = type("H", (server.Handler,), {"root": ROOT, "require_auth": False, "tls": False,
                                             "access_token": None, "guard": server.LoginGuard(),
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


def read_part(page, part):
    raw = page.evaluate("(p) => localStorage.getItem(p)", part)
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def nested_put(page, frame, part):
    frame.evaluate("""() => {
        const f = document.createElement('iframe');
        f.id = 't185-nested';
        f.srcdoc = '<body><p>nested</p></body>';
        document.body.appendChild(f);
    }""")
    frame.wait_for_selector("#t185-nested", timeout=5000)
    child = next(c for c in frame.child_frames if c.name == "t185-nested")
    child.wait_for_function("() => document.readyState === 'complete'", timeout=10000)
    child.evaluate("() => parent.parent.postMessage({aimem:'store.v1',op:'put',key:'stats',value:'1'},'*')")
    page.wait_for_timeout(400)
    after = read_part(page, part)
    return after.get("stats") != "1", f"stats={after.get('stats')!r}"


def popup_put(ctx, page, frame, part):
    try:
        with ctx.expect_page(timeout=4000) as info:
            frame.evaluate("() => window.open('about:blank')")
        popup = info.value
        popup.evaluate("""() => {
            opener.postMessage({aimem:'store.v1',op:'put',key:'frpop',value:'1'},'*');
            opener.parent.postMessage({aimem:'store.v1',op:'put',key:'frpop2',value:'1'},'*');
        }""")
        page.wait_for_timeout(400)
        after = read_part(page, part)
        passed = after.get("frpop") != "1" and after.get("frpop2") != "1"
        detail = f"팝업 열림; opener={after.get('frpop')!r}, opener.parent={after.get('frpop2')!r}"
        popup.close()
        return passed, detail
    except Exception as exc:
        return True, f"window.open 막힘/열리지 않음({type(exc).__name__}) - 막힌 것도 방어"


def self_put(page, part):
    page.evaluate("window.postMessage({aimem:'store.v1',op:'put',key:'self',value:'1'},'*')")
    page.wait_for_timeout(400)
    after = read_part(page, part)
    return after.get("self") != "1", f"self={after.get('self')!r}"


def bad_keys(page, frame, part):
    long_key = "a" * 300
    frame.evaluate("(key) => parent.postMessage({aimem:'store.v1',op:'put',key:key,value:'1'},'*')", "../other")
    frame.evaluate("(key) => parent.postMessage({aimem:'store.v1',op:'put',key:key,value:'1'},'*')", long_key)
    page.wait_for_timeout(400)
    after = read_part(page, part)
    bad = "../other" in after or long_key in after
    return not bad, f"bad_key_present={bad}"


def big_value(page, frame, part):
    big = "x" * 8193
    frame.evaluate("(value) => parent.postMessage({aimem:'store.v1',op:'put',key:'big',value:value},'*')", big)
    page.wait_for_timeout(400)
    after = read_part(page, part)
    stored = after.get("big")
    return stored is None, f"big={stored!r}" if stored is not None else "big 없음"


def scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 420, "height": 900})
    page = ctx.new_page()
    page.goto(base + "/", wait_until="load")
    page.click("#tab-projects")      # 프로젝트가 별도 탭이 됐다 (2026-11-12)
    page.wait_for_selector("#projects-list .proj-run", timeout=10000)
    page.locator("#projects-list .proj-run").first.click()
    page.wait_for_selector("iframe.proj-app-frame", timeout=10000)
    page.wait_for_function(
        "() => { const f = document.querySelector('iframe.proj-app-frame'); return !!(f && f.contentWindow); }",
        timeout=10000,
    )
    frame = next(f for f in page.frames if "/app/" in f.url)
    frame.wait_for_function("() => document.readyState === 'complete'", timeout=10000)
    src = page.locator("iframe.proj-app-frame").get_attribute("src")
    part = "aimem.app.v1." + src.split("/app/")[1].rstrip("/")

    checks_list = [
        ("중첩 iframe의 put은 무시된다", lambda: nested_put(page, frame, part)),
        ("팝업의 put은 무시된다", lambda: popup_put(ctx, page, frame, part)),
        ("모니터 자신의 put은 무시된다", lambda: self_put(page, part)),
        ("키 꼴이 아닌 것은 거절된다", lambda: bad_keys(page, frame, part)),
        ("8,192자를 넘는 값은 저장되지 않는다", lambda: big_value(page, frame, part)),
    ]
    for goal, fn in checks_list:
        try:
            passed, detail = fn()
        except Exception as exc:
            passed, detail = False, f"{type(exc).__name__}: {exc}"
        checks.ok(goal, passed, detail)
    ctx.close()


def main():
    checks = Checks()
    try:
        with monitor_server() as base:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    scenario(browser, base, checks)
                finally:
                    browser.close()
    except Exception as exc:
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
