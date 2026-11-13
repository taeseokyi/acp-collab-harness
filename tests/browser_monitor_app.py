#!/usr/bin/env python3
"""T-131 브라우저 실측: /app/웹워들/이 브라우저에서 어떻게 그려지는지 8문항을 잰다."""
import pathlib
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from aimem_monitor import server          # noqa: E402
import _monitor_fixture                   # noqa: E402


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


def scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 420, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    resp = page.goto(base + "/app/웹워들/", wait_until="load")
    page.wait_for_selector("#board .tile", timeout=10000)
    try:
        page.wait_for_selector("#modal-help:not([hidden])", timeout=3000)
    except Exception:
        pass
    else:
        page.click("#modal-help .modal-close")
        page.wait_for_function("() => document.getElementById('modal-help').hidden === true")

    tiles = page.locator("#board .tile")
    checks.ok("보드가 30칸", tiles.count() == 30, f"실제 {tiles.count()}")

    board_box = page.locator("#board").bounding_box()
    visible = bool(board_box) and board_box["width"] > 0 and board_box["height"] > 0
    checks.ok("보드가 눈에 보인다", visible,
              f"보임={visible}, box={board_box}" if board_box else "보임=False, box=None")

    kb_box = page.locator("#keyboard").bounding_box()
    if board_box and kb_box:
        b_top, b_bottom = board_box["y"], board_box["y"] + board_box["height"]
        k_top, k_bottom = kb_box["y"], kb_box["y"] + kb_box["height"]
        no_overlap = b_bottom <= k_top + 1 or k_bottom <= b_top + 1
    else:
        no_overlap = False
    checks.ok("보드와 화면 키보드가 겹치지 않는다", no_overlap, f"board={board_box}, keyboard={kb_box}")

    offscreen = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    checks.ok("화면 밖으로 삐져나오지 않는다", bool(offscreen), f"scrollWidth<=innerWidth+1={offscreen}")

    page.keyboard.type("crane")
    row1 = page.locator("#board .row:nth-child(1) .tile")
    typed = page.evaluate(
        "() => Array.from(document.querySelectorAll('#board .row:nth-child(1) .tile')).map(t => t.textContent).join('')"
    )
    checks.ok("글자를 치면 보인다", typed == "CRANE", f"첫 줄={typed!r}")

    first_tile = row1.nth(0)
    before = first_tile.evaluate("el => getComputedStyle(el).backgroundColor")
    page.keyboard.press("Enter")
    page.wait_for_timeout(2000)
    after = first_tile.evaluate("el => getComputedStyle(el).backgroundColor")
    checks.ok("제출하면 색이 실제로 칠해진다", before != after, f"제출 전={before} 제출 후={after}")

    csp = resp.header_value("content-security-policy") or ""
    checks.ok("CSP frame-ancestors 'self'", "frame-ancestors 'self'" in csp and "frame-ancestors 'none'" not in csp,
              csp or "헤더 없음")

    checks.ok("자바스크립트 오류 없음", not errors, "; ".join(errors[:3]))
    ctx.close()


def main():
    checks = Checks()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _monitor_fixture.write_wordle_project(tmp)         # 운영 projects/ 를 읽지 않는다
            with _monitor_fixture.serve(server, tmp) as (_, base):
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
