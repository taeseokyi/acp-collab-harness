#!/usr/bin/env python3
"""모니터의 프로젝트 '실행' 단추가 격리된 iframe 미리보기를 여는지 브라우저에서 잽니다."""
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
    """인증 끈 평문 http 모니터를 임시 포트에 띄웁니다. root 를 주면 그 폴더를 읽습니다."""
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
        page.click("#tab-projects")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)
        # 진행 중 프로젝트가 있으면 처음 필터가 '진행 중' 이라 끝난 웹워들이 숨는다 - 전체로 (2026-11-12)
        page.locator("#projects-filter-chips .chip").filter(has_text="전체").first.click()

        project = page.locator("#projects-list .proj-item").filter(has_text="웹워들").first
        run_button = project.locator(".proj-run").first
        run_visible = run_button.is_visible()
        run_text = run_button.inner_text().strip() if run_visible else ""
        checks.ok(
            "'앱 열기' 단추가 눈에 보인다",
            run_visible and run_text == "앱 열기 ▶",
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


def narrow_scenario(browser, base, checks):
    """폰 폭(390x844)에서 미리보기가 좁은 화면 규칙대로 그려지는가."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.click("#tab-projects")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)
        project = page.locator("#projects-list .proj-item").filter(has_text="웹워들").first
        project.locator(".proj-run").first.click()
        page.wait_for_selector("iframe.proj-app-frame", state="visible", timeout=15000)
        iframe = page.locator("iframe.proj-app-frame").first
        box = iframe.bounding_box()

        height = box["height"] if box else None
        target = min(0.70 * 844, 640)
        checks.ok(
            "폰 폭에서 미리보기 높이가 좁은 화면 규칙을 따른다",
            height is not None and abs(height - target) <= 2,
            f"height={height}px, target={target}px (기본 규칙이 이기면 658px)",
        )

        body_box = page.locator("#detail-body").bounding_box()
        contained = box is not None and body_box is not None and contains(box, body_box)
        checks.ok(
            "폰 폭에서 패널 밖으로 잘리지 않는다",
            contained,
            f"iframe={box}, detail-body={body_box}",
        )

        scroll = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        checks.ok(
            "폰 폭에서 가로 스크롤이 생기지 않는다",
            scroll <= 1,
            f"document.scrollWidth - innerWidth = {scroll}px",
        )
    finally:
        ctx.close()


def short_scenario(browser, base, checks):
    """짧은 화면(844x390)에서 미리보기 최소 높이가 결과물 키 크기를 지켜 주는가."""
    ctx = browser.new_context(viewport={"width": 844, "height": 390})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.click("#tab-projects")
        page.wait_for_selector("#projects-list .proj-item", timeout=15000)
        project = page.locator("#projects-list .proj-item").filter(has_text="웹워들").first
        project.locator(".proj-run").first.click()
        page.wait_for_selector("iframe.proj-app-frame", state="visible", timeout=15000)
        box = page.locator("iframe.proj-app-frame").first.bounding_box()
        key = page.frame_locator("iframe.proj-app-frame").locator(".key").first
        key.wait_for(state="visible", timeout=20000)
        key_box = key.bounding_box()
        checks.ok(
            "짧은 화면에서도 결과물 키가 32px 이상이다",
            box is not None and key_box is not None and box["height"] >= 426 and key_box["height"] >= 32,
            f"iframe 높이={box and round(box['height'], 1)}, 키 높이={key_box and round(key_box['height'], 1)}",
        )
    finally:
        ctx.close()


def changed_ui_scenario(browser, base, checks):
    """바뀐 화면 다섯 가지를 브라우저에서 실제로 잽니다."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#aimem-meta .meta-goal", state="visible", timeout=15000)

        card = page.query_selector("#kisti-section")
        inner_card = page.query_selector("#kisti-card")
        fleet_titles = page.eval_on_selector_all(
            "#panel-fleet .card h2", "els => els.map(e => e.textContent.trim())"
        )
        kisti_titles = [t for t in fleet_titles if t.startswith("KISTI")]
        checks.ok(
            "KISTI 카드가 화면에 없다",
            card is None and inner_card is None and not kisti_titles,
            f"#kisti-section={card}, #kisti-card={inner_card}, "
            f"함대 카드 h2={fleet_titles}, KISTI로 시작={kisti_titles}",
        )

        meta = page.locator("#aimem-meta")
        meta_text = meta.inner_text()
        label = page.locator(".meta-goal .meta-label").first
        value = page.locator(".meta-goal .goal-value").first
        label_text = label.inner_text().strip()
        value_text = value.inner_text().strip()
        checks.ok(
            "'이번 라운드'가 보이고 내용이 있다",
            meta.is_visible()
            and "현재 목표" not in meta_text
            and label.is_visible()
            and label_text == "이번 라운드"
            and value.is_visible()
            and value_text not in ("", "-"),
            f"meta visible={meta.is_visible()}, '현재 목표'={('현재 목표' in meta_text)}, "
            f"label={label_text!r}, value={value_text!r}",
        )

        page.set_viewport_size({"width": 390, "height": 780})
        page.click("#tab-board")
        page.wait_for_selector("#panel-board", state="visible", timeout=15000)
        candidates = page.query_selector_all(
            "#board-section .elide[role=button], #queue-section .elide[role=button]"
        )
        el = None
        sw_before = cw_before = None
        for cand in candidates:
            if not cand.is_visible():
                continue
            sw = cand.evaluate("e=>e.scrollWidth")
            cw = cand.evaluate("e=>e.clientWidth")
            if sw > cw:
                el = cand
                sw_before, cw_before = sw, cw
                break

        if el is None:
            checks.ok(
                "생략된 제목을 눌러 펼칠 수 있다 (폰 폭 390px)",
                False,
                "잘린 .elide[role=button]을 보드·큐에서 찾지 못함",
            )
        else:
            box_before = el.bounding_box()
            el.click()
            page.wait_for_selector(".elide.elide-open", timeout=3000)
            class_after = el.get_attribute("class") or ""
            box_after = el.bounding_box()
            sw_after = el.evaluate("e=>e.scrollWidth")
            cw_after = el.evaluate("e=>e.clientWidth")
            overlay = page.query_selector("#detail-overlay")
            overlay_display = overlay.evaluate("e=>getComputedStyle(e).display") if overlay else "missing"
            scroll = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            checks.ok(
                "생략된 제목을 눌러 펼칠 수 있다 (폰 폭 390px)",
                box_before is not None
                and box_after is not None
                and box_after["height"] > box_before["height"]
                and "elide-open" in class_after.split()
                and sw_after <= cw_after + 1
                and overlay_display == "none"
                and scroll == 0,
                f"전: scrollWidth={sw_before}, clientWidth={cw_before}, height={box_before and round(box_before['height'], 2)}; "
                f"후: class={class_after!r}, scrollWidth={sw_after}, clientWidth={cw_after}, "
                f"height={box_after and round(box_after['height'], 2)}; overlay={overlay_display}, 가로스크롤={scroll}px",
            )
    finally:
        ctx.close()


def write_fixed_requests(root):
    """서브태스크 0건인 요청 네 건을 임시 저장소에 씁니다."""
    req_dir = root / ".aimem" / "requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    for status in ("NEW", "PLANNED", "IN-PROGRESS", "DONE"):
        data = {
            "id": f"Q-FIXED-{status}",
            "title": f"임시 요청 {status}",
            "status": status,
            "created": "2026-11-01T00:00:00",
            "updated": "2026-11-01T00:00:00",
            "requester": "tester",
            "subtasks": [],
        }
        (req_dir / f"Q-FIXED-{status}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_fixed_graph(root):
    """제목이 아주 긴, 아직 끝나지 않은 그래프 하나를 임시 저장소에 씁니다."""
    gdir = root / ".aimem" / "graph"
    gdir.mkdir(parents=True, exist_ok=True)
    long_title = (
        "임시 저장소 고정 그래프의 아주 긴 제목입니다 "
        + "가나다라마바사아자차카타파하" * 14
    )
    data = {
        "id": "G-FIXED",
        "request": long_title,
        "created": "2026-11-12T00:00:00",
        "updated": "2026-11-12T00:00:00",
        "rev": 159,
        "round": 17,
        "concurrency": 1,
        "nodes": [
            {
                "id": "T-900",
                "slot": "S3",
                "deps": [],
                "status": "todo",
                "title": "임시 저장소 고정 그래프 노드",
                "attempts": [],
                "max_attempts": 2,
            },
            {
                "id": "T-901",
                "slot": "S3",
                "deps": ["T-900"],
                "status": "done",
                "title": "임시 저장소 고정 그래프 완료 노드",
                "attempts": [],
                "max_attempts": 2,
            },
        ],
    }
    (gdir / "G-FIXED.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def write_fixed_runs(root):
    """프로젝트가 붙은 실행과 안 붙은 실행을 임시 저장소에 하나씩 씁니다."""
    runs_dir = root / ".aimem" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for run_id, project, label in (
        ("T-901-S3-a1-000001", "데모프로젝트", "임시 실행 (프로젝트 있음)"),
        ("T-901-S3-a1-000002", "", "임시 실행 (프로젝트 없음)"),
    ):
        data = {
            "id": run_id,
            "slot": "S3",
            "harness": "opencode",
            "task": "T-901",
            "attempt": 1,
            "date": "2026-11-01",
            "label": label,
            "rev": 159,
            "write": [],
            "started": "2026-11-01T00:00:01",
            "project": project,
            "round": 9,
        }
        (runs_dir / f"{run_id}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        (runs_dir / f"{run_id}.rc").write_text("0\n", encoding="utf-8")


def zero_subtask_scenario(browser, base, checks):
    """임시 저장소의 고정 요청 네 건으로 서브태스크 0건 화면을 잽니다."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.wait_for_selector("#tab-requests", state="visible", timeout=15000)
        page.click("#tab-requests")
        page.wait_for_selector("#requests-list .req-block", state="visible", timeout=15000)

        bad = []
        open_seen = []
        for block in page.query_selector_all("#requests-list .req-block"):
            badge = block.query_selector(".badge")
            status = badge.inner_text().strip() if badge else ""
            if status not in ("NEW", "PLANNED", "IN-PROGRESS"):
                continue
            open_seen.append(status)
            progress = block.query_selector_all(".req-progress")
            etas = block.query_selector_all(".eta")
            wait_line = block.query_selector(".req-wait-line")
            empty = block.query_selector(".req-body .empty")
            explained = (wait_line is not None and wait_line.is_visible()) or (
                empty is not None and empty.is_visible()
            )
            if progress or etas or not block.is_visible() or not explained:
                bad.append((status, len(progress), len(etas), block.is_visible(), explained))

        closed_fold = page.locator("#requests-list .closed-fold").first
        closed_fold_visible = closed_fold.is_visible()
        if closed_fold_visible:
            closed_fold.click()

        done_blocks = []
        for block in page.query_selector_all("#requests-list .req-block"):
            badge = block.query_selector(".badge")
            status = badge.inner_text().strip() if badge else ""
            if status != "DONE":
                continue
            done_blocks.append(block)
            if block.query_selector_all(".req-progress") or block.query_selector_all(".eta"):
                bad.append(("DONE", "진행률·ETA 있음"))

        done_detail = ""
        if done_blocks:
            done_blocks[0].query_selector(".req-toggle").click()
            for block in page.query_selector_all("#requests-list .req-block"):
                badge = block.query_selector(".badge")
                status = badge.inner_text().strip() if badge else ""
                if status != "DONE":
                    continue
                done_line = block.query_selector(".req-done-line")
                text = block.inner_text()
                if done_line is not None and done_line.is_visible():
                    done_detail = text[:200]
                    if (
                        block.query_selector_all(".req-progress")
                        or block.query_selector_all(".eta")
                        or "100%" in text
                        or "서브태스크 없이 끝난 요청입니다" in text
                    ):
                        bad.append(("DONE", "펼친 뒤 진행률·ETA·옛 문구"))
                    break

        checks.ok(
            "서브태스크 없는 요청에는 진행률·ETA가 없다 (임시 저장소)",
            closed_fold_visible
            and sorted(open_seen) == ["IN-PROGRESS", "NEW", "PLANNED"]
            and bool(done_blocks)
            and done_detail
            and not bad,
            f"열린 요청={open_seen}, 닫힌 접기 visible={closed_fold_visible}, "
            f"DONE 블록={len(done_blocks)}개, 펼친 DONE={done_detail!r}, 어긋남={bad}",
        )
    finally:
        ctx.close()


def request_tree_scenario(browser, base, checks):
    """요청 트리 탭의 정리 패널·접기·DONE 표시·겹침을 브라우저에서 잽니다."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        archive_button = page.locator("#archive-open").first
        fleet_visible = archive_button.is_visible()
        page.click("#tab-requests")
        page.wait_for_selector("#requests-list .req-block", state="visible", timeout=15000)

        tools = page.locator("#requests-tools")
        tools_text = tools.inner_text()
        count_match = re.search(r"끝난 요청\s*(\d+)\s*건", tools_text)
        requests_visible = archive_button.is_visible()
        checks.ok(
            "요청 트리에서도 정리할 수 있다",
            fleet_visible
            and requests_visible
            and tools.is_visible()
            and count_match is not None
            and int(count_match.group(1)) > 0,
            f"함대 탭 단추 visible={fleet_visible}, 요청 트리 단추 visible={requests_visible}, "
            f"tools visible={tools.is_visible()}, 글={tools_text!r}, "
            f"끝난 요청 수={count_match.group(1) if count_match else None}",
        )

        archive_button.click()
        panel = page.locator("#detail-overlay")
        panel.locator("h2").first.wait_for(state="visible", timeout=10000)
        title = panel.locator("h2").first.inner_text()
        panel_checks = []
        for keyword in ("실행 기록", "이벤트", "핸드오프"):
            found = any(
                li.is_visible() and keyword in li.inner_text()
                for li in panel.locator(".archive-intro li").all()
            )
            panel_checks.append((keyword, found))
        page.wait_for_selector(".archive-out p.hint", state="visible", timeout=15000)
        preview_line = page.locator(".archive-out p.hint").first
        preview_text = preview_line.inner_text()
        runs_match = re.search(r"실행 기록\s+(\d+)건", preview_text)
        events_match = re.search(r"이벤트\s+(\d+)건", preview_text)
        checks.ok(
            "패널이 새 종류를 설명한다",
            all(found for _, found in panel_checks)
            and preview_line.is_visible()
            and runs_match is not None
            and events_match is not None,
            f"설명 {panel_checks}, 미리보기 줄={preview_text!r}",
        )

        page.locator("#detail-close").click()
        panel.locator("h2").first.wait_for(state="hidden", timeout=5000)

        closed_fold = page.locator("#requests-list .closed-fold").first
        fold_visible = closed_fold.is_visible()
        closed_visible = []
        for block in page.query_selector_all("#requests-list .req-block"):
            badge = block.query_selector(".badge")
            status = badge.inner_text().strip() if badge else ""
            if status in ("DONE", "REJECTED") and block.is_visible():
                closed_visible.append(status)
        checks.ok(
            "끝난 것이 접혀 있다",
            fold_visible and not closed_visible,
            f"closed-fold visible={fold_visible}, 처음 보이는 닫힌 블록={closed_visible}",
        )

        closed_fold.click()
        page.wait_for_timeout(500)

        def visible_closed():
            result = []
            for block in page.query_selector_all("#requests-list .req-block"):
                badge = block.query_selector(".badge")
                status = badge.inner_text().strip() if badge else ""
                if status in ("DONE", "REJECTED") and block.is_visible():
                    result.append(status)
            return result

        first_open = visible_closed()
        page.wait_for_timeout(6000)
        later_open = visible_closed()
        checks.ok(
            "펼치면 보이고, 5초 뒤에도 그대로다",
            bool(first_open) and bool(later_open),
            f"펼친 뒤={len(first_open)}개, 6초 뒤={len(later_open)}개",
        )

        done_ok = False
        done_bad = []
        done_text = ""
        for block in page.query_selector_all("#requests-list .req-block"):
            badge = block.query_selector(".badge")
            status = badge.inner_text().strip() if badge else ""
            if status != "DONE":
                continue
            if block.query_selector_all(".req-progress") or block.query_selector_all(".eta"):
                done_bad.append("접힌 DONE: 진행률·ETA 있음")
            text = block.inner_text()
            if "100%" in text or "서브태스크 없이 끝난 요청입니다" in text:
                done_bad.append("접힌 DONE: 100%/옛 문구 있음")

        for block in page.query_selector_all("#requests-list .req-block"):
            badge = block.query_selector(".badge")
            status = badge.inner_text().strip() if badge else ""
            if status != "DONE":
                continue
            toggle = block.query_selector(".req-toggle")
            toggle.click()
            break

        for block in page.query_selector_all("#requests-list .req-block"):
            badge = block.query_selector(".badge")
            status = badge.inner_text().strip() if badge else ""
            if status != "DONE":
                continue
            done_line = block.query_selector(".req-done-line")
            text = block.inner_text()
            if done_line is None or not done_line.is_visible():
                done_bad.append("펼친 DONE: .req-done-line 없음")
                continue
            if block.query_selector_all(".req-progress") or block.query_selector_all(".eta"):
                done_bad.append("펼친 DONE: 진행률·ETA 있음")
            if "100%" in text or "서브태스크 없이 끝난 요청입니다" in text:
                done_bad.append("펼친 DONE: 100%/옛 문구 있음")
            done_ok = True
            done_text = text[:200]
            break

        checks.ok(
            "DONE 요청에 100%·ETA가 없다",
            done_ok and not done_bad,
            f"펼친 DONE={done_text!r}, 어긋남={done_bad}",
        )

        page.evaluate("window.scrollTo(0, 0)")
        tools_box = tools.bounding_box()
        first_box = page.locator("#requests-list .req-block").first.bounding_box()
        no_overlap = (
            tools_box is not None
            and first_box is not None
            and (
                tools_box["y"] + tools_box["height"] <= first_box["y"]
                or first_box["y"] + first_box["height"] <= tools_box["y"]
            )
        )
        page.set_viewport_size({"width": 390, "height": 780})
        page.wait_for_timeout(300)
        scroll = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        checks.ok(
            "겹치지 않고 밖으로 안 나간다",
            no_overlap and scroll == 0,
            f"tools={tools_box}, 첫 블록={first_box}, 겹침없음={no_overlap}, "
            f"390px 가로스크롤={scroll}px",
        )

        page.click("#tab-board")
        page.wait_for_selector("#board-filter button", state="visible", timeout=15000)
        archive_like = page.locator("#board-filter button").filter(has_text="끝난 것 정리")
        checks.ok(
            "보드 필터줄에 '끝난 것 정리' 단추가 없다",
            archive_like.count() == 0,
            f"#board-filter 안에 '끝난 것 정리' 글자를 가진 단추={archive_like.count()}개",
        )
    finally:
        ctx.close()


def graph_title_expand_scenario(browser, base, checks):
    """폰 폭(390x844)에서 그래프 제목을 눌러 펼치고, 다시 그려도 유지되는가."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.click("#tab-requests")
        try:
            page.wait_for_selector("#graphs-list .graph-title", state="visible", timeout=15000)
        except Exception:
            checks.ok("그래프 제목 펼치기", False, "그래프 없음")
            return

        title = page.locator("#graphs-list .graph-title").first
        visible = title.is_visible()
        class_before = title.get_attribute("class") or ""
        aria_before = title.get_attribute("aria-expanded")
        sw = title.evaluate("e => e.scrollWidth")
        cw = title.evaluate("e => e.clientWidth")
        box_before = title.bounding_box()
        checks.ok(
            "그래프 제목이 처음에는 줄여져 있다 (폰 폭 390px)",
            visible
            and "elide-open" not in class_before.split()
            and (sw > cw + 1 or aria_before == "false"),
            f"visible={visible}, class={class_before!r}, aria-expanded={aria_before!r}, "
            f"scrollWidth={sw}, clientWidth={cw}",
        )

        title.click()
        page.wait_for_timeout(300)
        class_after = title.get_attribute("class") or ""
        aria_after = title.get_attribute("aria-expanded")
        box_after = title.bounding_box()
        checks.ok(
            "누르면 그래프 제목이 펼쳐진다",
            "elide-open" in class_after.split()
            and aria_after == "true"
            and box_before is not None
            and box_after is not None
            and box_after["height"] > box_before["height"],
            f"전 높이={box_before and round(box_before['height'], 2)}, "
            f"후 class={class_after!r}, aria-expanded={aria_after!r}, "
            f"후 높이={box_after and round(box_after['height'], 2)}",
        )

        checks.ok(
            "펼친 그래프 제목이 화면 밖으로 나가지 않는다",
            box_after is not None
            and box_after["x"] >= -1
            and box_after["x"] + box_after["width"] <= 390 + 1,
            f"box={box_after}",
        )

        page.wait_for_timeout(6000)
        later = page.locator("#graphs-list .graph-title").first
        class_later = later.get_attribute("class") or ""
        checks.ok(
            "5초 뒤 다시 그려도 펼친 채다",
            "elide-open" in class_later.split(),
            f"class={class_later!r}, aria-expanded={later.get_attribute('aria-expanded')!r}",
        )

        later.click()
        page.wait_for_timeout(300)
        class_final = later.get_attribute("class") or ""
        aria_final = later.get_attribute("aria-expanded")
        checks.ok(
            "다시 누르면 그래프 제목이 접힌다",
            "elide-open" not in class_final.split() and aria_final == "false",
            f"class={class_final!r}, aria-expanded={aria_final!r}",
        )
    finally:
        ctx.close()


def run_project_tag_scenario(browser, base, checks):
    """임시 저장소의 고정 실행 기록으로 프로젝트 칸의 볼드 기준을 잽니다."""
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    try:
        page.goto(base + "/", wait_until="load")
        page.click("#tab-fleet")
        page.wait_for_selector("#runs-table-wrap", state="visible", timeout=15000)
        project_names = page.query_selector_all("#runs-table-wrap .proj-tag:not(.none) .proj-name")
        none_names = page.query_selector_all("#runs-table-wrap .proj-tag.none .proj-name")
        rounds = page.query_selector_all("#runs-table-wrap .proj-round")

        def weight(el):
            return int(el.evaluate("e=>getComputedStyle(e).fontWeight"))

        project_weights = [weight(e) for e in project_names]
        none_weights = [weight(e) for e in none_names]
        round_weights = [weight(e) for e in rounds]
        checks.ok(
            "프로젝트 칸의 볼드 기준",
            bool(project_names)
            and bool(none_names)
            and bool(rounds)
            and all(w >= 700 for w in project_weights)
            and all(w <= 500 for w in none_weights)
            and all(w <= 500 for w in round_weights),
            f"프로젝트 이름 {project_weights}, 프로젝트 없음 {none_weights}, 라운드 꼬리표 {round_weights}",
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
                    scenario(browser, base, checks)
                    narrow_scenario(browser, base, checks)
                    short_scenario(browser, base, checks)
                    changed_ui_scenario(browser, base, checks)
                    request_tree_scenario(browser, base, checks)

                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_root = pathlib.Path(temp_dir)
                    write_fixed_requests(temp_root)
                    write_fixed_graph(temp_root)
                    write_fixed_runs(temp_root)
                    with monitor_server(root=temp_root) as temp_base:
                        zero_subtask_scenario(browser, temp_base, checks)
                        graph_title_expand_scenario(browser, temp_base, checks)
                        run_project_tag_scenario(browser, temp_base, checks)
            finally:
                browser.close()
    except Exception as exc:
        checks.ok("검사 실행", False, f"{type(exc).__name__}: {exc}")
    return checks.finish()


if __name__ == "__main__":
    raise SystemExit(main())
