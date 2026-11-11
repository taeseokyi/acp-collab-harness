#!/usr/bin/env python3
"""모니터의 프로젝트 '실행' 단추가 격리된 iframe 미리보기를 여는지 브라우저에서 잽니다."""
import http.server
import pathlib
import sys
import threading
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

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
def monitor_server():
    """인증 끈 평문 http 모니터를 임시 포트에 띄웁니다."""
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


def contains(inner, outer, tolerance=2):
    return (
        inner["x"] >= outer["x"] - tolerance
        and inner["y"] >= outer["y"] - tolerance
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + tolerance
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + tolerance
    )


def scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)

        project = page.locator("#projects-list .proj-item").filter(has_text="웹워들").first
        run_button = project.locator(".proj-run").first
        run_visible = run_button.is_visible()
        run_text = run_button.inner_text().strip() if run_visible else ""
        checks.ok(
            "'실행' 단추가 눈에 보인다",
            run_visible and run_text == "실행",
            f"visible={run_visible}, text={run_text!r}",
        )

        preview_error = ""
        if run_visible:
            run_button.click()
            try:
                page.wait_for_selector("iframe.proj-app-frame", state="visible", timeout=15000)
            except Exception as exc:
                preview_error = f"{type(exc).__name__}: {exc}"

        iframe = page.locator("iframe.proj-app-frame").first
        iframe_visible = iframe.is_visible()
        iframe_box = iframe.bounding_box()
        iframe_height = iframe_box["height"] if iframe_box is not None else None
        preview_ok = iframe_visible and iframe_height is not None and iframe_height >= 300
        detail = f"visible={iframe_visible}, box={iframe_box}"
        if preview_error:
            detail += f", 대기 오류={preview_error}"
        checks.ok("누르면 미리보기 칸이 보인다", preview_ok, detail)

        sandbox = iframe.get_attribute("sandbox") if iframe_visible else None
        tokens = sandbox.split() if sandbox else []
        checks.ok(
            "격리가 살아 있다 (allow-scripts 있고 allow-same-origin 없음)",
            "allow-scripts" in tokens and "allow-same-origin" not in tokens,
            f"sandbox={sandbox!r}",
        )

        frame = page.frame_locator("iframe.proj-app-frame")
        tiles = frame.locator("#board .tile")
        inner_ok = False
        inner_detail = ""
        try:
            tiles.first.wait_for(state="visible", timeout=20000)
            tile_count = tiles.count()
            first_visible = tiles.first.is_visible()
            inner_ok = tile_count == 30 and first_visible
            inner_detail = f"타일 {tile_count}개, 첫 칸 visible={first_visible}"
        except Exception as exc:
            inner_detail = f"대기 오류={type(exc).__name__}: {exc}"
        checks.ok("안쪽 보드가 진짜로 그려졌다", inner_ok, inner_detail)

        body_box = page.locator("#detail-body").bounding_box()
        contained = iframe_box is not None and body_box is not None and contains(iframe_box, body_box)
        checks.ok(
            "패널 밖으로 잘리지 않는다",
            contained,
            f"iframe={iframe_box}, detail-body={body_box}",
        )

        link = page.locator("#detail-body a[target=_blank]").first
        link_visible = link.is_visible()
        href = link.get_attribute("href") or ""
        rel = link.get_attribute("rel") or ""
        rel_tokens = rel.lower().split()
        checks.ok(
            "'새 탭에서 열기' 링크가 보이고 안전하게 열린다",
            link_visible and href.startswith("/app/") and "noopener" in rel_tokens,
            f"visible={link_visible}, href={href!r}, rel={rel!r}",
        )
    finally:
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
