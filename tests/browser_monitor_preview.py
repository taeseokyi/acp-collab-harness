#!/usr/bin/env python3
"""T-184 브라우저 실측: 모니터 미리보기 칸에서 보관함 기록이 남고 칸이 섞이지 않는지 잰다."""
import re
import http.server
import json
import pathlib
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager
from urllib.parse import quote

from playwright.sync_api import expect, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import server          # noqa: E402


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
def monitor_server(root):
    """인증 끈 평문 http 모니터를 임시 포트에 띄웁니다."""
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
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def part_for(name):
    return "aimem.app.v1." + quote(name, safe="")


def open_preview(page, name=None, wait_selector="#board .tile"):
    # 프로젝트 탭은 처음에 '진행 중' 만 보인다 - 끝난 웹워들도 보이게 '전체' 로 (2026-11-12).
    # 단추 글자는 '실행' → '앱 열기 ▶' 로 바뀌었다 - 글자 대신 class 로 찾는다
    # 진행 중 프로젝트가 앞에 오도록 정렬되므로 '첫 단추' 가 아니라 이름이 정확히 같은 카드를 찾는다
    all_chip = page.locator("#projects-filter-chips .chip", has_text="전체").first
    if all_chip.count() and all_chip.get_attribute("aria-pressed") != "true":
        all_chip.click()
    target = name or "웹워들"
    card = page.locator("#projects-list article").filter(
        has=page.locator("h3", has_text=re.compile("^" + re.escape(target) + "$")))
    card.locator(".proj-run").first.click()
    page.wait_for_selector("iframe.proj-app-frame", timeout=10000)
    iframe = page.locator("iframe.proj-app-frame").first
    frame = iframe.element_handle().content_frame()
    frame.wait_for_selector(wait_selector, timeout=10000)
    return frame


def close_help(frame):
    modal = frame.locator("#modal-help")
    try:
        expect(modal).to_be_visible(timeout=1000)
    except Exception:
        return
    frame.click("#modal-help .modal-close")
    expect(modal).to_be_hidden(timeout=2000)


def open_settings(frame):
    frame.click("#btn-settings")
    expect(frame.locator("#modal-settings")).to_be_visible(timeout=3000)


def close_settings(frame):
    frame.click("#modal-settings .modal-close")
    expect(frame.locator("#modal-settings")).to_be_hidden(timeout=2000)


def close_panel(page):
    page.click("#detail-close")
    expect(page.locator("#detail-overlay")).to_be_hidden(timeout=3000)


def webwordle_checks(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 420, "height": 900})
    page = ctx.new_page()
    part = part_for("웹워들")
    f = None
    setup_error = ""
    try:
        page.goto(base + "/", wait_until="load")
        page.click("#tab-projects")      # 프로젝트가 별도 탭이 됐다 (2026-11-12)
        page.wait_for_selector("#projects-list", timeout=10000)
        f = open_preview(page)
        close_help(f)
        page.wait_for_function(
            "(p) => { const o=JSON.parse(localStorage.getItem(p)||'{}'); return o.seenHelp === 'true'; }",
            arg=part, timeout=5000)
        open_settings(f)
        f.click("#set-dark")
        page.wait_for_function(
            "(p) => { const o=JSON.parse(localStorage.getItem(p)||'{}'); if (!o.settings) return false;"
            " const s=JSON.parse(o.settings); return s.dark === true; }", arg=part, timeout=5000)
        close_settings(f)
    except Exception as exc:
        setup_error = f"{type(exc).__name__}: {exc}"[:180]
    if f is None:
        for goal in ("한 판 첫 줄이 실제 글자로 C R A N E",
                     "패널을 닫았다 다시 열어도 첫 줄이 남는다",
                     "어두운 테마 설정이 다시 열어도 켜져 있다"):
            checks.ok(goal, False, setup_error)
        return ctx, page

    goal1 = "한 판 첫 줄이 실제 글자로 C R A N E"
    try:
        f.locator("#board").click()
        page.keyboard.type("crane")
        expect(f.locator("#board .row:nth-child(1) .tile")).to_have_text(
            ["C", "R", "A", "N", "E"], timeout=5000)
        checks.ok(goal1, True)
    except Exception as exc:
        checks.ok(goal1, False, f"{type(exc).__name__}: {exc}"[:180])

    goal2 = "패널을 닫았다 다시 열어도 첫 줄이 남는다"
    f2 = None
    try:
        page.keyboard.press("Enter")
        page.wait_for_function(
            "(p) => { const o=JSON.parse(localStorage.getItem(p)||'{}');"
            " return Object.keys(o).some(k=>k.startsWith('daily.')); }", arg=part, timeout=6000)
        close_panel(page)
        f2 = open_preview(page)
        close_help(f2)
        expect(f2.locator("#board .row:nth-child(1) .tile")).to_have_text(
            ["C", "R", "A", "N", "E"], timeout=6000)
        checks.ok(goal2, True)
    except Exception as exc:
        checks.ok(goal2, False, f"{type(exc).__name__}: {exc}"[:180])

    goal3 = "어두운 테마 설정이 다시 열어도 켜져 있다"
    try:
        if f2 is None:
            raise RuntimeError("새 미리보기 칸을 열지 못했습니다")
        open_settings(f2)
        checked = f2.locator("#set-dark").is_checked()
        checks.ok(goal3, checked, f"checked={checked}")
        close_settings(f2)
    except Exception as exc:
        checks.ok(goal3, False, f"{type(exc).__name__}: {exc}"[:180])

    try:
        close_panel(page)
    except Exception:
        pass
    return ctx, page


def fake_checks(page, checks):
    web_part = part_for("웹워들")
    fake_name = "웹워들-가짜"
    fake_part = part_for(fake_name)
    goal4 = "가짜 프로젝트 스냅숏에 웹워들 키가 없다"
    goal5 = "가짜 put 값이 웹워들 칸에 나타나지 않는다"
    try:
        f = open_preview(page, fake_name, wait_selector="#snap")
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"[:180]
        checks.ok(goal4, False, detail)
        checks.ok(goal5, False, detail)
        return

    try:
        expect(f.locator("#snap")).not_to_have_text("waiting", timeout=6000)
        text = f.locator("#snap").inner_text().strip()
        items = json.loads(text)
        keys = sorted(items) if isinstance(items, dict) else []
        forbidden = {"seenHelp", "settings", "fakeKey"} | {k for k in keys if k.startswith("daily.")}
        clean = isinstance(items, dict) and not (set(keys) & forbidden)
        checks.ok(goal4, clean, f"snapshot={text!r}")
    except Exception as exc:
        checks.ok(goal4, False, f"{type(exc).__name__}: {exc}"[:180])

    try:
        f.evaluate("() => parent.postMessage({aimem:'store.v1',op:'put',key:'fakeKey',value:'\\\"fake\\\"'}, '*')")
        page.wait_for_function(
            "(p) => { const o=JSON.parse(localStorage.getItem(p)||'{}');"
            " return Object.prototype.hasOwnProperty.call(o,'fakeKey'); }", arg=fake_part, timeout=5000)
        web_raw = page.evaluate("(p) => localStorage.getItem(p)||''", web_part)
        fake_raw = page.evaluate("(p) => localStorage.getItem(p)||''", fake_part)
        checks.ok(goal5, "fakeKey" not in web_raw and "fakeKey" in fake_raw,
                  f"web={web_raw[:120]!r} fake={fake_raw[:120]!r}")
    except Exception as exc:
        checks.ok(goal5, False, f"{type(exc).__name__}: {exc}"[:180])


def main():
    checks = Checks()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="aimem-preview-"))
    root = tmp / "root"
    try:
        (root / "projects").mkdir(parents=True)
        shutil.copytree(ROOT / "projects/웹워들", root / "projects/웹워들")

        fake_dir = root / "projects/웹워들-가짜"
        (fake_dir / "web").mkdir(parents=True)
        (fake_dir / "app.json").write_text(
            '{"title":"가짜","root":"web","entry":"index.html"}', encoding="utf-8")
        (fake_dir / "web/index.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>가짜</title><body>'
            '<pre id="snap">waiting</pre><script src="fake.js"></script></body>', encoding="utf-8")
        (fake_dir / "web/fake.js").write_text(
            'const snap=document.getElementById("snap");'
            'addEventListener("message",e=>{const d=e.data;'
            'if(d&&d.aimem==="store.v1"&&d.op==="snapshot")snap.textContent=JSON.stringify(d.items);});'
            'parent.postMessage({aimem:"store.v1",op:"ready"},"*");', encoding="utf-8")

        (root / ".aimem").mkdir()
        for name in ("aimem.db", "aimem.db-wal", "aimem.db-shm"):
            src = ROOT / ".aimem" / name
            if src.exists():
                shutil.copy2(src, root / ".aimem" / name)

        try:
            with monitor_server(root) as base, sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    _, page = webwordle_checks(browser, base, checks)
                    fake_checks(page, checks)
                finally:
                    browser.close()
        except Exception as exc:
            checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
