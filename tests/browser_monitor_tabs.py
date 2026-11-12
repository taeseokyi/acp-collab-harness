#!/usr/bin/env python3
"""모니터의 프로젝트 탭·전역 정리 단추·작업 요청 프로젝트 고르기를 브라우저에서 잽니다."""
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
def monitor_server(root=None):
    root = pathlib.Path(root) if root is not None else ROOT
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


def tab_texts(page):
    return page.eval_on_selector_all(
        ".tabs [role=tab]",
        "els => els.map((el) => { const n = el.firstChild; return n && n.nodeType === 3 ? n.textContent.trim() : ''; })",
    )


def visible_panel_count(page):
    return page.eval_on_selector_all(
        "[role=tabpanel]",
        "els => els.filter((el) => el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0).length",
    )


def tabs_scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")

        tabs = page.locator(".tabs [role=tab]")
        texts = tab_texts(page)
        checks.ok(
            "탭이 넷이고 차례가 맞다",
            tabs.count() == 4
            and all(tabs.nth(i).is_visible() for i in range(tabs.count()))
            and texts == ["함대", "프로젝트", "보드·큐", "요청 트리"],
            f"count={tabs.count()}, visible={[tabs.nth(i).is_visible() for i in range(tabs.count())]}, texts={texts}",
        )

        checks.ok(
            "처음에는 프로젝트 카드가 함대 탭에 안 보인다",
            not page.locator("#projects-section").is_visible(),
            f"#projects-section visible={page.locator('#projects-section').is_visible()}",
        )

        page.click("#tab-projects")
        project_wait_error = ""
        try:
            page.wait_for_selector("#projects-list .proj-item", state="visible", timeout=15000)
        except Exception as exc:
            project_wait_error = f"{type(exc).__name__}: {exc}"
        items = page.locator("#projects-list .proj-item")
        any_item_visible = any(items.nth(i).is_visible() for i in range(items.count()))
        section_visible = page.locator("#projects-section").is_visible()
        fleet_visible = page.locator("#panel-fleet").is_visible()
        detail = f"section={section_visible}, items={items.count()}, any_visible={any_item_visible}, fleet={fleet_visible}"
        if project_wait_error:
            detail += f", 대기 오류={project_wait_error}"
        checks.ok(
            "프로젝트 탭을 누르면 보인다",
            section_visible and any_item_visible and not fleet_visible,
            detail,
        )

        per_tab = []
        for tab_id in ("#tab-fleet", "#tab-projects", "#tab-board", "#tab-requests"):
            page.click(tab_id)
            per_tab.append((tab_id, visible_panel_count(page)))
        checks.ok(
            "보이는 패널은 늘 정확히 하나다",
            all(count == 1 for _, count in per_tab),
            f"{per_tab}",
        )

        page.goto(base + "/#tab=projects", wait_until="load")
        page.reload(wait_until="load")
        selected = page.locator("#tab-projects").get_attribute("aria-selected")
        panel_visible = page.locator("#panel-projects").is_visible()
        checks.ok(
            "주소로 바로 열린다",
            selected == "true" and panel_visible,
            f"aria-selected={selected!r}, panel-projects visible={panel_visible}",
        )

        archive_states = []
        for tab_id in ("#tab-fleet", "#tab-projects", "#tab-board", "#tab-requests"):
            page.click(tab_id)
            archive_states.append((tab_id, page.locator("#archive-open").is_visible()))
        board_archive_buttons = page.locator("#board-filter button").filter(has_text="끝난 것 정리").count()
        checks.ok(
            "전역 정리 단추가 어느 탭에서나 보인다",
            all(visible for _, visible in archive_states) and board_archive_buttons == 0,
            f"archive-open={archive_states}, board-filter 정리 단추={board_archive_buttons}",
        )

        page.click("#archive-open")
        label = page.locator("#detail-overlay h2").first
        label_wait_error = ""
        try:
            label.wait_for(state="visible", timeout=10000)
        except Exception as exc:
            label_wait_error = f"{type(exc).__name__}: {exc}"
        label_visible = label.is_visible()
        label_text = label.inner_text().strip() if label_visible else ""
        page.click("#detail-close")
        overlay_hidden = not page.locator("#detail-overlay").is_visible()
        detail = f"h2 visible={label_visible}, text={label_text!r}, 닫은 뒤 overlay visible={not overlay_hidden}"
        if label_wait_error:
            detail += f", 대기 오류={label_wait_error}"
        checks.ok(
            "누르면 정리 패널이 열린다",
            label_visible and "정리" in label_text and overlay_hidden,
            detail,
        )
    finally:
        ctx.close()


def project_picker_scenario(browser, base, checks):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        wait_error = ""
        try:
            page.wait_for_selector("#projects-list .proj-item", state="attached", timeout=15000)
            page.wait_for_selector(
                "#req-project-pick option:not([value='']):not([value='__new__'])",
                state="attached",
                timeout=15000,
            )
        except Exception as exc:
            wait_error = f"{type(exc).__name__}: {exc}"

        sel = page.locator("#req-project-pick")
        sel_visible = sel.is_visible()
        values = page.locator("#req-project-pick option").evaluate_all("opts => opts.map((o) => o.value)")
        names = page.locator("#projects-list .proj-item h3").evaluate_all(
            "els => els.map((e) => e.textContent.trim())"
        )
        name_in_values = any(name in values for name in names)
        detail = f"visible={sel_visible}, values={values}, project names={names}"
        if wait_error:
            detail += f", 대기 오류={wait_error}"
        checks.ok(
            "고를 거리가 보인다",
            sel_visible and len(values) >= 3 and "" in values and "__new__" in values and name_in_values,
            detail,
        )

        page.select_option("#req-project-pick", "__new__")
        input_visible = page.locator("#req-project").is_visible()
        page.select_option("#req-project-pick", "")
        input_hidden = not page.locator("#req-project").is_visible()
        checks.ok(
            "'+ 새 프로젝트…' 를 고르면 입력칸이 나타난다",
            input_visible and input_hidden,
            f"__new__ 일 때 visible={input_visible}, 빈 값으로 되돌린 뒤 visible={not input_hidden}",
        )

        page.select_option("#req-project-pick", "__new__")
        page.fill("#req-project", "아주-긴-프로젝트-이름-테스트-12345")
        pick_box = sel.bounding_box()
        input_box = page.locator("#req-project").bounding_box()

        def in_width(box):
            return box is not None and box["x"] >= -1 and box["x"] + box["width"] <= 390 + 1

        def no_overlap(a, b):
            return a is not None and b is not None and (
                a["y"] + a["height"] <= b["y"] + 0.5 or b["y"] + b["height"] <= a["y"] + 0.5
            )

        checks.ok(
            "글자를 넣어도 칸이 화면 밖으로 안 나간다",
            in_width(pick_box) and in_width(input_box) and no_overlap(pick_box, input_box),
            f"pick={pick_box}, input={input_box}",
        )
    finally:
        ctx.close()


def main():
    checks = Checks()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                with monitor_server() as base:
                    tabs_scenario(browser, base, checks)
                    project_picker_scenario(browser, base, checks)
            finally:
                browser.close()
    except Exception as exc:
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
