#!/usr/bin/env python3
"""모니터의 프로젝트 탭·전역 정리 단추·작업 요청 프로젝트 고르기를 브라우저에서 잽니다."""
import http.server
import json
import pathlib
import sys
import tempfile
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
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def write_fixed_repo(root):
    """임시 저장소에 고정 프로젝트 둘을 씁니다 - 하나는 진행 중, 하나는 끝남."""
    root = pathlib.Path(root)
    req_dir = root / ".aimem" / "requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    fixed = (
        ("임시-진행-프로젝트", "IN-PROGRESS", "Q-FIXED-PROGRESS"),
        ("임시-끝난-프로젝트", "DONE", "Q-FIXED-DONE"),
        ("임시-진행-프로젝트", "NEW", "Q-FIXED-NEW"),
    )
    for name, status, req_id in fixed:
        pdir = root / "projects" / name
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "PROGRESS.md").write_text(f"# {name}\n", encoding="utf-8")
        data = {
            "id": req_id,
            "title": f"임시 요청 {status}",
            "status": status,
            "created": "2026-11-01T00:00:00",
            "updated": "2026-11-01T00:00:00",
            "requester": "tester",
            "project": name,
            "subtasks": [],
        }
        (req_dir / f"{req_id}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )


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


def edit_picker_scenario(browser, base, checks):
    """요청 수정 폼의 프로젝트 고르기는 작업 요청 폼과 같은 함수다 - 현재 값을 고른 채 열리고 '+ 새 프로젝트…' 로 입력칸이 나온다."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.click("#tab-requests")
        page.wait_for_selector("#requests-list .req-edit-btn", state="visible", timeout=15000)
        page.locator("#requests-list .req-edit-btn").first.click()
        sel = page.locator(".req-edit-project-pick")
        sel.wait_for(state="visible", timeout=5000)
        values = sel.locator("option").evaluate_all("opts => opts.map((o) => o.value)")
        cur = sel.input_value()
        shown = page.locator(".req-edit-project").is_visible()
        sel.select_option("__new__")
        after_new = page.locator(".req-edit-project").is_visible()
        sel.select_option("")
        after_none = page.locator(".req-edit-project").is_visible()
        checks.ok("요청 수정 폼의 프로젝트 고르기",
                  cur == "임시-진행-프로젝트" and "" in values and "__new__" in values and not shown and after_new and not after_none,
                  f"현재={cur!r}, 값={values}, 처음 입력칸={shown}, 새 프로젝트={after_new}, 비움={after_none}")
    finally:
        ctx.close()


def tab_counts_scenario(browser, base, checks):
    """탭 숫자의 규칙: 함대 = 실행 중 작업자(관리자 제외), 보드·큐 = 미완료 태스크만(큐는 큐 머리글에), 정리 단추 = 끝난 요청+그래프."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    def state_route(route):
        r = route.fetch()
        d = r.json()
        run = lambda i, role, state: {"id": f"r{i}", "slot": "S1", "harness": "x", "model": "m", "label": "t", "started": "2026-11-13T10:00:00",  # noqa: E731
                                      "state": state, "rc": None, "elapsed_sec": 5, "report_head": "", "role": role,
                                      "session_state": state, "last_event_at": None, "last_event": None}
        d["runs"] = [run(1, "worker", "running"), run(2, "manager", "running"), run(3, "worker", "done")]
        d["board"] = [{"id": f"T-{i}", "task": "x", "slot": "S1", "status": st, "handoff": "-", "artifact": ""}
                      for i, st in enumerate(("TODO", "REVIEW", "DONE", "BLOCKED"))]
        d["queue"] = [{"order": str(i), "task": "x", "slots": "S1", "handoff": "", "note": ""} for i in range(1, 4)]
        route.fulfill(response=r, body=json.dumps(d), content_type="application/json")
    page.route("**/api/state*", state_route)
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#tab-count-fleet", state="attached", timeout=15000)
        page.wait_for_function("() => document.getElementById('tab-count-fleet').textContent.trim() !== ''", timeout=15000)
        txt = lambda i: page.locator(i).inner_text().strip()  # noqa: E731
        checks.ok("탭 숫자: 함대는 실행 중 작업자만 (관리자 제외)", txt("#tab-count-fleet") == "1", txt("#tab-count-fleet"))
        checks.ok("탭 숫자: 보드·큐는 미완료 태스크만 (3), 큐 건수는 큐 머리글에 (3)",
                  txt("#tab-count-board") == "3" and txt("#queue-count") == "3", f"{txt('#tab-count-board')} / {txt('#queue-count')}")
        sec = page.locator("#runs-table-wrap").locator("xpath=ancestor::section[1]//h2").first.inner_text()
        checks.ok("실행 표 머리글은 '실행 상태'", sec.strip().startswith("실행 상태"), sec)
    finally:
        ctx.close()


def main():
    checks = Checks()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_root = pathlib.Path(temp_dir)
                    write_fixed_repo(temp_root)
                    with monitor_server(root=temp_root) as base:
                        tabs_scenario(browser, base, checks)
                        project_picker_scenario(browser, base, checks)
                        edit_picker_scenario(browser, base, checks)
                        tab_counts_scenario(browser, base, checks)
            finally:
                browser.close()
    except Exception as exc:
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
