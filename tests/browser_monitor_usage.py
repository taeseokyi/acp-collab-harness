#!/usr/bin/env python3
"""모니터의 Claude 사용 한도 카드를 브라우저에서 잽니다 (T-233)."""
import datetime as dt
import http.server
import json
import pathlib
import re
import sys
import tempfile
import threading
from contextlib import contextmanager
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from aimem_monitor import server
KEYS = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"]
LABELS = ["5시간", "주간", "주간·Opus", "주간·Sonnet"]
PCTS = ["40%", "85%", "97%", "12%"]
CLASSES = ["usage-ok", "usage-warn", "usage-crit", "usage-ok"]
RATIOS = [0.40, 0.85, 0.97, 0.12]
class Checks:
    def __init__(self): self.results = []
    def ok(self, goal, cond, detail=""): self.results.append((bool(cond), goal, detail))
    def finish(self):
        failures = sum(not p for p, _, _ in self.results)
        for p, goal, detail in self.results:
            print(f"[{'OK' if p else 'FAIL'}] {goal}" + (f" - {detail}" if detail else ""))
        print(f"통과 {len(self.results) - failures} / 전체 {len(self.results)}")
        return failures
@contextmanager
def monitor_server(root=None):
    root = pathlib.Path(root) if root is not None else ROOT
    handler = type("H", (server.Handler,), {"root": root, "require_auth": False, "tls": False,
                                            "access_token": None, "guard": server.LoginGuard(),
                                            "timeout": 5, "log_message": lambda *a, **k: None})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try: yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=3)
def usage_root(rows, at=None):
    d = pathlib.Path(tempfile.mkdtemp(prefix="r18-usage-"))
    (d / ".aimem").mkdir()
    at = at or dt.datetime.now().isoformat(timespec="seconds")
    (d / ".aimem" / "claude-usage.json").write_text(
        json.dumps({"at": at, "rate_limits": rows}, ensure_ascii=False), encoding="utf-8")
    return d
def base_rows():
    t = dt.datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
    return {
        "five_hour": {"used_percentage": 40.0, "resets_at": t.isoformat()},
        "seven_day": {"used_percentage": 85.0, "resets_at": t.replace(hour=20, minute=30).isoformat()},
        "seven_day_opus": {"used_percentage": 97.0, "resets_at": t.replace(hour=21, minute=10).isoformat()},
        "seven_day_sonnet": {"used_percentage": 12.0},
    }
def wait_for(page, selector, timeout=5000):
    try: page.wait_for_selector(selector, state="attached", timeout=timeout); return ""
    except Exception as exc: return f"{type(exc).__name__}: {exc}"
def safe_text(loc): return loc.inner_text().strip() if loc.count() else ""
def box_of(loc): return loc.bounding_box() if loc.count() else None
def x_overlap(a, b, tol=0.5):
    return not (a["x"] + a["width"] <= b["x"] + tol or b["x"] + b["width"] <= a["x"] + tol)
def fleet_scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        wait_error = wait_for(page, "#usage-section")
        section, fleet = page.locator("#usage-section"), page.locator("#fleet-section")
        sb, fb = box_of(section), box_of(fleet)
        checks.ok("사용 한도 카드가 함대 탭에서 보이고 함대 현황보다 위에 있다",
                  section.is_visible() and page.locator("#panel-fleet").is_visible()
                  and sb is not None and fb is not None and sb["y"] < fb["y"],
                  f"visible={section.is_visible()}, section={sb}, fleet={fb}, 대기={wait_error}")
        rows = page.locator(".usage-row")
        keys = page.eval_on_selector_all(".usage-row", "els => els.map(e => e.dataset.key || '')")
        checks.ok("사용 행이 넷이고 차례가 맞다", rows.count() == 4 and keys == KEYS,
                  f"count={rows.count()}, keys={keys}")
        labels = page.eval_on_selector_all(".usage-label", "els => els.map(e => e.textContent.trim())")
        checks.ok("라벨 글이 맞다", labels == LABELS, f"labels={labels}")
        pcts = page.eval_on_selector_all(".usage-pct", "els => els.map(e => e.textContent.trim())")
        checks.ok("퍼센트 글이 맞다", pcts == PCTS, f"pcts={pcts}")
        ratios = []
        for i, t in enumerate(RATIOS):
            bb = box_of(rows.nth(i).locator(".usage-bar"))
            ff = box_of(rows.nth(i).locator(".usage-fill"))
            ratios.append(ff["width"] / bb["width"] if bb and ff and bb["width"] else None)
        checks.ok("그려진 막대 너비가 퍼센트를 따른다",
                  all(r is not None and abs(r - t) <= 0.05 for r, t in zip(ratios, RATIOS)),
                  f"ratios={ratios}")
        cls = page.eval_on_selector_all(
            ".usage-row", "els => els.map(e => e.className.split(/\\s+/).filter(Boolean))")
        checks.ok("행의 평상/주의/경고 클래스가 맞다",
                  len(cls) == 4 and all(c in cl for cl, c in zip(cls, CLASSES)), f"classes={cls}")
        colors = page.eval_on_selector_all(
            ".usage-row .usage-fill", "els => els.map(e => getComputedStyle(e).backgroundColor)")
        checks.ok("세 상태의 막대 색이 서로 다르다", len(colors) >= 3 and len(set(colors[:3])) == 3,
                  f"colors={colors}")
        sonnet = rows.nth(3).locator(".usage-reset").count()
        others = [rows.nth(i).locator(".usage-reset") for i in range(3)]
        checks.ok("초기화 시각이 있는 행과 없는 행이 맞다",
                  sonnet == 0 and all(l.count() == 1 and safe_text(l).startswith("초기화 ") for l in others),
                  f"sonnet={sonnet}, others={[(l.count(), safe_text(l)) for l in others]}")
        five = rows.nth(0).locator(".usage-reset")
        checks.ok("five_hour 초기화 글이 오늘 꼴이다",
                  five.count() == 1 and re.fullmatch(r"초기화 \d{1,2}:\d{2}", safe_text(five)) is not None,
                  f"text={safe_text(five)!r}")
    finally: ctx.close()
def rounding_scenario(browser, checks):
    rows = base_rows()
    rows["five_hour"]["used_percentage"] = 79.6
    with monitor_server(root=usage_root(rows)) as base:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(base + "/", wait_until="load")
            wait_for(page, "#usage-section")
            row = page.locator(".usage-row").first
            pct = safe_text(row.locator(".usage-pct"))
            checks.ok("퍼센트는 소수 한 자리를 반올림해 80%로 찍는다", pct == "80%", f"pct={pct!r}")
            cls = row.evaluate("e => e.className.split(/\\s+/).filter(Boolean)")
            checks.ok("79.6% 행은 아직 usage-ok이다", "usage-ok" in cls, f"classes={cls}")
        finally: ctx.close()
def stale_scenario(browser, checks):
    now = dt.datetime.now()
    def read(root):
        with monitor_server(root=root) as base:
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            try:
                page.goto(base + "/", wait_until="load")
                wait_for(page, "#usage-section")
                return safe_text(page.locator("#usage-stale"))
            finally: ctx.close()
    def read_age(seconds):
        at = (now - dt.timedelta(seconds=seconds)).isoformat(timespec="seconds")
        return read(usage_root(base_rows(), at=at))
    stale = read(usage_root(base_rows(), at=(now - dt.timedelta(minutes=30)).isoformat(timespec="seconds")))
    fresh = read(usage_root(base_rows(), at=now.isoformat(timespec="seconds")))
    checks.ok("오래된 자료는 'N분 전 기준'을 보이고 지금 자료는 비어 있다",
              stale != "" and "분 전 기준" in stale and fresh == "",
              f"30분 전={stale!r}, 지금={fresh!r}")
    sixty = read_age(60 * 60 + 5)
    sixty_one = read_age(61 * 60 + 5)
    checks.ok("정확히 60분 전 기준은 '60분 전 기준'이다", sixty == "60분 전 기준", f"60분={sixty!r}")
    checks.ok("61분 전 기준은 '1시간 전 기준'이다", sixty_one == "1시간 전 기준", f"61분={sixty_one!r}")
def empty_scenario(browser, checks):
    root = pathlib.Path(tempfile.mkdtemp(prefix="r18-usage-empty-"))
    (root / ".aimem").mkdir()
    with monitor_server(root=root) as base:
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(base + "/", wait_until="load")
            wait_for(page, "#usage-section")
            empty = page.locator("#claude-usage .empty")
            checks.ok("사용 자료가 없으면 상태줄 안내가 보이고 행은 없다",
                      empty.count() == 1 and empty.is_visible()
                      and "상태줄" in safe_text(empty) and page.locator(".usage-row").count() == 0,
                      f"empty={empty.count()}, visible={empty.is_visible()}, text={safe_text(empty)!r}")
        finally: ctx.close()
def narrow_scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        wait_for(page, "#usage-section")
        sb = box_of(page.locator("#usage-section"))
        row = page.locator(".usage-row").first
        parts = [row.locator(".usage-label"), row.locator(".usage-bar"),
                 row.locator(".usage-pct"), row.locator(".usage-reset")]
        boxes = [box_of(l) for l in parts]
        no_overlap = all(boxes) and all(
            not x_overlap(boxes[i], boxes[j])
            for i in range(len(boxes)) for j in range(i + 1, len(boxes)))
        inside = sb is not None and all(
            b is not None and b["x"] + b["width"] <= sb["x"] + sb["width"] + 1 for b in boxes)
        checks.ok("390px 폭에서 한 행의 요소가 겹치지 않고 카드 밖으로 안 나간다",
                  no_overlap and inside, f"section={sb}, boxes={boxes}")
    finally: ctx.close()
def scroll_scenario(browser, base, checks):
    results = []
    for width in (1280, 390):
        ctx = browser.new_context(viewport={"width": width, "height": 900})
        page = ctx.new_page()
        try:
            page.goto(base + "/", wait_until="load")
            wait_for(page, "#usage-section")
            m = page.evaluate(
                "(() => { const d = document.documentElement; return {sw: d.scrollWidth, cw: d.clientWidth}; })()")
            results.append((width, page.locator("#usage-section").count(), m["sw"], m["cw"]))
        finally: ctx.close()
    checks.ok("1280px와 390px 모두에서 카드가 가로 스크롤을 만들지 않는다",
              all(count == 1 and sw <= cw + 1 for _, count, sw, cw in results),
              f"results={results}")
def main():
    checks = Checks()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                with monitor_server(root=usage_root(base_rows())) as base:
                    fleet_scenario(browser, base, checks)
                    narrow_scenario(browser, base, checks)
                    scroll_scenario(browser, base, checks)
                rounding_scenario(browser, checks)
                stale_scenario(browser, checks)
                empty_scenario(browser, checks)
            finally: browser.close()
    except Exception as exc:
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    return checks.finish()
if __name__ == "__main__":
    raise SystemExit(main())
